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
        ).where(DocumentChunk.version_id == version.id)
    ).all()

    historical_product_ids = {
        row.product_id.strip()
        for row in rows
        if row.product_id and row.product_id.strip()
    }

    historical_categories = {
        row.category.strip() for row in rows if row.category and row.category.strip()
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
        select(Document).where(Document.id == document.id).with_for_update()
    )

    if locked_document is None:
        raise ValueError("Document does not exist.")

    latest_version_number = db.scalar(
        select(DocumentVersion.version_number)
        .where(DocumentVersion.document_id == locked_document.id)
        .order_by(DocumentVersion.version_number.desc())
        .limit(1)
    )

    next_version_number = (
        1 if latest_version_number is None else latest_version_number + 1
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

    Only previous active versions of the SAME document
    are superseded.

    Different documents remain active, even when they
    share the same product ID or category.

    The caller must commit the transaction.
    """

    version = db.scalar(
        select(DocumentVersion)
        .where(DocumentVersion.id == version_id)
        .with_for_update()
    )

    if version is None:
        raise ValueError(f"Document version {version_id} not found.")

    document = db.scalar(
        select(Document).where(Document.id == version.document_id).with_for_update()
    )

    if document is None:
        raise ValueError("Document associated with this version was not found.")

    if version.is_active:
        raise ValueError("This version is already active.")

    if version.status not in {"processing", "completed", "ready"}:
        raise ValueError(f"Cannot activate version with status '{version.status}'.")

    product_id = version.product_id
    category = normalize_category(version.category)
    file_path = version.file_path

    if not category:
        raise ValueError("Version-specific category is required.")

    if not file_path:
        raise ValueError("Version-specific file path is required.")

    file_type = version.file_type or Path(file_path).suffix.lstrip(".").lower()

    if not file_type:
        raise ValueError("Version file type is required.")

    # Find previous active versions of this same document.
    previous_versions = db.scalars(
        select(DocumentVersion)
        .where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.id != version.id,
            DocumentVersion.is_active.is_(True),
        )
        .with_for_update()
    ).all()

    for old_version in previous_versions:
        old_version.is_active = False
        old_version.status = "superseded"

    db.flush()

    # Activate the newly processed version.
    version.is_active = True
    version.status = "active"
    version.error_message = None

    # Synchronize parent document metadata.
    document.product_id = product_id
    document.category = category
    document.file_path = file_path
    document.file_type = file_type
    document.status = "active"

    db.flush()
