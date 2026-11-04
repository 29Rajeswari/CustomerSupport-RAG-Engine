
from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.config import PROJECT_ROOT, settings
from app.db.models import Document, DocumentVersion
from app.ingestion.versioning import (
    create_document_version,
    normalize_category,
)

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".txt"}


def validate_document_file(filename: str) -> str:
    """Validate the file extension and return it in lowercase."""
    extension = Path(filename).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise ValueError(
            f"Unsupported file type '{extension}'. "
            f"Allowed types: {allowed}"
        )

    return extension


def get_upload_directory() -> Path:
    """Resolve the configured upload directory."""
    upload_dir = Path(settings.UPLOAD_DIR)

    if not upload_dir.is_absolute():
        upload_dir = PROJECT_ROOT / upload_dir

    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


def save_uploaded_file(filename: str, content: bytes) -> Path:
    """Save file bytes using a unique server-generated filename."""
    extension = validate_document_file(filename)

    if not isinstance(content, bytes):
        raise TypeError("File content must be bytes.")

    if not content:
        raise ValueError("Uploaded file is empty.")

    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    if len(content) > max_bytes:
        raise ValueError(
            f"File exceeds the maximum size of "
            f"{settings.MAX_UPLOAD_SIZE_MB} MB."
        )

    upload_dir = get_upload_directory()
    destination = upload_dir / f"{uuid4().hex}{extension}"

    try:
        with destination.open("xb") as file:
            file.write(content)
    except Exception:
        if destination.exists():
            destination.unlink()
        raise

    return destination


def create_document_record(
    db: Session,
    title: str,
    filename: str,
    category: str,
    product_id: str | None = None,
    file_path: str | Path | None = None,
) -> tuple[Document, DocumentVersion]:
    """
    Create a document record and its first processing version.

    Both the parent document and its first version receive
    their own file metadata.

    The caller is responsible for committing the transaction.
    """
    extension = validate_document_file(filename)

    stored_path = str(file_path) if file_path is not None else ""

    document = Document(
        title=title.strip(),
        category=normalize_category(category),
        product_id=product_id,
        file_path=stored_path,
        file_type=extension.lstrip("."),
        status="processing",
    )

    db.add(document)
    db.flush()

    version = create_document_version(db, document)

    # Store metadata specifically on the new version.
    version.file_path = stored_path
    version.file_type = extension.lstrip(".")
    version.category = normalize_category(category)
    version.product_id = product_id

    db.flush()

    return document, version
