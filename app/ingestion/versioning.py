
# app/ingestion/versioning.py

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Document,
    DocumentChunk,
    DocumentVersion,
)


def normalize_category(category: str | None) -> str:
    """Normalize category names and common spelling variations."""
    value = (category or "").strip().casefold()

    if value in {"warrenty", "warranty"}:
        return "warranty"

    return value


def _get_version_metadata(
    db: Session,
    version: DocumentVersion,
) -> tuple[str | None, str | None]:
    """
    Get version metadata.

    For historical versions whose metadata columns are NULL,
    use chunk metadata only when it contains one unambiguous value.
    """
    product_id = version.product_id
    category = version.category

    if product_id and category:
        return product_id, category

    rows = db.execute(
        select(
            DocumentChunk.product_id,
            DocumentChunk.category,
        ).where(
            DocumentChunk.version_id == version.id
        )
    ).all()

    historical_product_ids = {
        row.product_id.strip()
        for row in rows
        if row.product_id and row.product_id.strip()
    }

    historical_categories = {
        row.category.strip()
        for row in rows
        if row.category and row.category.strip()
    }

    if not product_id and len(historical_product_ids) == 1:
        product_id = next(iter(historical_product_ids))

    if not category and len(historical_categories) == 1:
        category = next(iter(historical_categories))

    return product_id, category


def create_document_version(
    db: Session,
    document: Document,
) -> DocumentVersion:
    """
    Create a new processing version for an existing document.

    The caller must set version-specific metadata and commit.
    """
    locked_document = db.scalar(
        select(Document)
        .where(Document.id == document.id)
        .with_for_update()
    )

    if locked_document is None:
        raise ValueError("Document does not exist.")

    latest_version_number = db.scalar(
        select(DocumentVersion.version_number)
        .where(
            DocumentVersion.document_id == locked_document.id
        )
        .order_by(DocumentVersion.version_number.desc())
        .limit(1)
    )

    next_version_number = (
        1 if latest_version_number is None
        else latest_version_number + 1
    )

    version = DocumentVersion(
        document_id=locked_document.id,
        version_number=next_version_number,
        status="processing",
        is_active=False,
    )

    db.add(version)
    db.flush()

    return version


def get_active_version(
    db: Session,
    document_id: int,
) -> DocumentVersion | None:
    """Return the active version for a document."""
    return db.scalar(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document_id,
            DocumentVersion.is_active.is_(True),
            DocumentVersion.status == "active",
        )
    )


def activate_version_and_supersede_conflicts(
    db: Session,
    version_id: int,
) -> None:
    """
    Activate a successfully ingested version.

    Supersede:
    1. Previous active versions of the same document.
    2. Active versions of other documents with the same product
       ID and normalized category.

    The caller must commit the transaction.
    """
    version = db.scalar(
        select(DocumentVersion)
        .where(DocumentVersion.id == version_id)
        .with_for_update()
    )

    if version is None:
        raise ValueError(
            f"Document version {version_id} not found."
        )

    document = db.scalar(
        select(Document)
        .where(Document.id == version.document_id)
        .with_for_update()
    )

    if document is None:
        raise ValueError(
            "Document associated with this version was not found."
        )

    if version.is_active:
        raise ValueError("This version is already active.")

    if version.status not in {"processing", "completed", "ready"}:
        raise ValueError(
            f"Cannot activate version with status '{version.status}'."
        )

    product_id = version.product_id
    category = version.category
    file_path = version.file_path

    if not product_id or not category:
        raise ValueError(
            "Version-specific product ID and category are required."
        )

    if not file_path:
        raise ValueError(
            "Version-specific file path is required."
        )

    file_type = (
        version.file_type
        or Path(file_path).suffix.lstrip(".").lower()
    )

    if not file_type:
        raise ValueError("Version file type is required.")

    category_key = normalize_category(category)

    # Load active versions and lock them before changing their status.
    active_versions = db.scalars(
        select(DocumentVersion)
        .where(
            DocumentVersion.id != version.id,
            DocumentVersion.is_active.is_(True),
            DocumentVersion.status == "active",
        )
        .with_for_update()
    ).all()

    affected_document_ids = set()

    for old_version in active_versions:
        # Older active versions of the same document must be
        # superseded even if the new version has different metadata.
        if old_version.document_id == document.id:
            old_version.is_active = False
            old_version.status = "superseded"
            affected_document_ids.add(old_version.document_id)
            continue

        # Other documents are superseded only when both their
        # product ID and normalized category match.
        old_product_id, old_category = _get_version_metadata(
            db,
            old_version,
        )

        if old_product_id != product_id:
            continue

        if normalize_category(old_category) != category_key:
            continue

        old_version.is_active = False
        old_version.status = "superseded"
        affected_document_ids.add(old_version.document_id)

    db.flush()

    # Mark old parent documents inactive only if they no longer
    # have any active versions.
    for old_document_id in affected_document_ids:
        if old_document_id == document.id:
            continue

        remaining_active = db.scalar(
            select(DocumentVersion.id)
            .where(
                DocumentVersion.document_id == old_document_id,
                DocumentVersion.is_active.is_(True),
                DocumentVersion.status == "active",
            )
            .limit(1)
        )

        if remaining_active is None:
            old_document = db.get(Document, old_document_id)

            if old_document is not None:
                old_document.status = "inactive"

    # Publish the new version and synchronize the parent document.
    version.is_active = True
    version.status = "active"
    version.error_message = None

    document.product_id = product_id
    document.category = category
    document.file_path = file_path
    document.file_type = file_type
    document.status = "active"

    db.flush()
