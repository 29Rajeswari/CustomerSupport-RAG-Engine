
import logging
from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_admin
from app.config import settings

from app.models import Document
from app.db.session import get_db

from app.ingestion.processor import process_document_version
from app.ingestion.versioning import (
    create_document_version,
    normalize_category,
)

from app.services.document_service import (
    create_document_record,
    save_uploaded_file,
    validate_document_file,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["Documents"])


def process_uploaded_version(version_id: int) -> None:
    """Run ingestion in a separate database session."""
    try:
        process_document_version(version_id)

        logger.info(
            "Document version %s processing finished.",
            version_id,
        )

    except Exception:
        logger.exception(
            "Failed to process document version %s.",
            version_id,
        )


def clean_required_field(value: str, field_name: str) -> str:
    """Reject blank fields and Swagger's default placeholder."""
    cleaned = value.strip()

    if not cleaned:
        raise ValueError(f"{field_name} cannot be empty.")

    if cleaned.casefold() == "string":
        raise ValueError(
            f"Replace the default 'string' value with a real {field_name}."
        )

    return cleaned


@router.post("/upload", status_code=201)
def upload_document(
    background_tasks: BackgroundTasks,
    title: str = Form(...),
    category: str = Form(...),
    product_id: str = Form(...),
    file: UploadFile = File(...),
    _: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
):

    """
    Upload a new document or create a new version.

    Every version stores its own file path and metadata.
    Ingestion runs automatically after the database commit.
    """
    saved_path: Path | None = None
    committed = False

    try:
        # 1. Validate required form fields.
        title = clean_required_field(title, "title")
        category = normalize_category(
            clean_required_field(category, "category")
        )
        product_id = clean_required_field(product_id, "product_id")

        original_filename = file.filename or ""
        extension = validate_document_file(original_filename)

        # 2. Read the uploaded file and enforce the size limit.
        max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        content = bytearray()

        while True:
            chunk = file.file.read(64 * 1024)

            if not chunk:
                break

            content.extend(chunk)

            if len(content) > max_bytes:
                raise HTTPException(
                    status_code=413,
                    detail=(
                        "File exceeds the maximum upload size of "
                        f"{settings.MAX_UPLOAD_SIZE_MB} MB."
                    ),
                )

        # 3. Save using a unique filename.
        saved_path = save_uploaded_file(
            original_filename,
            bytes(content),
        )

        # 4. Find an existing document.
        document = db.scalar(
            select(Document)
            .where(
                Document.product_id == product_id,
                func.lower(Document.title) == title.casefold(),
            )
            .with_for_update()
        )

        if document is None:
            # First upload.
            document, version = create_document_record(
                db=db,
                title=title,
                filename=original_filename,
                category=category,
                product_id=product_id,
                file_path=saved_path,
            )

            action = "created"

        else:
            # New version of an existing document.
            # Do not modify the parent Document metadata here.
            version = create_document_version(
                db=db,
                document=document,
            )

            # Store metadata on this specific version.
            version.file_path = str(saved_path)
            version.file_type = extension.lstrip(".")
            version.category = category
            version.product_id = product_id

            db.flush()

            action = "updated"

        # 5. Commit before scheduling background processing.
        db.commit()
        committed = True

        db.refresh(document)
        db.refresh(version)

        # 6. Schedule ingestion.
        background_tasks.add_task(
            process_uploaded_version,
            version.id,
        )

        return {
            "message": (
                "Document uploaded and processing scheduled."
                if action == "created"
                else "New document version uploaded and processing scheduled."
            ),
            "action": action,
            "document_id": document.id,
            "version_id": version.id,
            "version_number": version.version_number,
            "status": version.status,
            "filename": saved_path.name,
            "product_id": version.product_id,
            "category": version.category,
        }

    except HTTPException:
        if not committed:
            db.rollback()

            if saved_path is not None:
                saved_path.unlink(missing_ok=True)

        raise

    except ValueError as exc:
        if not committed:
            db.rollback()

            if saved_path is not None:
                saved_path.unlink(missing_ok=True)

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        if not committed:
            db.rollback()

            if saved_path is not None:
                saved_path.unlink(missing_ok=True)

        logger.exception("Document upload failed.")

        raise HTTPException(
            status_code=500,
            detail="Document upload failed.",
        ) from exc

    finally:
        file.file.close()
