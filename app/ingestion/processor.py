
# app/ingestion/processor.py

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.text_normalizer import normalize_text
from app.db.models import Document, DocumentChunk, DocumentVersion
from app.db.session import SessionLocal
from app.ingestion.parsers import extract_text
from app.ingestion.versioning import (
    activate_version_and_supersede_conflicts,
)
from app.llm.ollama_client import generate_embedding


CHUNK_SIZE = 1200
CHUNK_OVERLAP = 200
EXPECTED_EMBEDDING_DIMENSIONS = 768


def split_into_chunks(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[str]:
    """Split normalized text into overlapping chunks."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero.")

    if overlap < 0 or overlap >= chunk_size:
        raise ValueError(
            "overlap must be non-negative and smaller than chunk_size."
        )

    text = text.strip()

    if not text:
        return []

    chunks = []
    start = 0
    text_length = len(text)

    while start < text_length:
        end = min(start + chunk_size, text_length)

        if end < text_length:
            boundary = text.rfind(" ", start, end)

            if boundary > start + chunk_size // 2:
                end = boundary

        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        if end >= text_length:
            break

        start = max(end - overlap, start + 1)

    return chunks


def _get_document_and_version(
    db: Session,
    version_id: int,
) -> tuple[Document, DocumentVersion]:
    """Load a document and its requested version."""
    version = db.scalar(
        select(DocumentVersion).where(
            DocumentVersion.id == version_id
        )
    )

    if version is None:
        raise ValueError(
            f"Document version {version_id} was not found."
        )

    document = db.scalar(
        select(Document).where(
            Document.id == version.document_id
        )
    )

    if document is None:
        raise ValueError(
            f"Parent document for version {version_id} was not found."
        )

    return document, version


def process_document_version(version_id: int) -> int:
    """
    Process a document version and activate it after successful ingestion.

    Version-specific metadata is used throughout processing.

    The previous active version remains active if extraction,
    normalization, chunking, embedding, or activation fails.
    """

    # ---------------------------------------------------------
    # 1. Load version-specific information.
    # ---------------------------------------------------------
    with SessionLocal() as db:
        document, version = _get_document_and_version(
            db,
            version_id,
        )

        if version.is_active:
            raise ValueError(
                "This version is already active. Create a new version "
                "to process an updated document."
            )

        if version.status == "superseded":
            raise ValueError(
                "A superseded version cannot be processed."
            )

        document_id = document.id

        version_file_path = version.file_path
        version_product_id = version.product_id
        version_category = version.category

    try:
        # -----------------------------------------------------
        # 2. Validate version metadata and file.
        # -----------------------------------------------------
        if not version_file_path:
            raise ValueError(
                "The document version does not have a file path."
            )

        if not version_product_id:
            raise ValueError(
                "The document version does not have a product ID."
            )

        if not version_category:
            raise ValueError(
                "The document version does not have a category."
            )

        file_path = Path(version_file_path)

        if not file_path.is_file():
            raise FileNotFoundError(
                f"Document file does not exist: {file_path}"
            )

        # -----------------------------------------------------
        # 3. Extract and normalize document text.
        # -----------------------------------------------------
        extracted_text = extract_text(file_path)

        normalized_text = normalize_text(extracted_text)

        if not normalized_text:
            raise ValueError(
                "The document contains no searchable text."
            )

        # -----------------------------------------------------
        # 4. Split normalized text into chunks.
        # -----------------------------------------------------
        chunks = split_into_chunks(normalized_text)

        if not chunks:
            raise ValueError("No chunks were generated.")

        # -----------------------------------------------------
        # 5. Generate and validate embeddings.
        # Do this before changing any active version.
        # -----------------------------------------------------
        prepared_chunks = []

        for index, chunk in enumerate(chunks):
            embedding = generate_embedding(chunk)

            if len(embedding) != EXPECTED_EMBEDDING_DIMENSIONS:
                raise ValueError(
                    f"Chunk {index}: expected "
                    f"{EXPECTED_EMBEDDING_DIMENSIONS} embedding dimensions, "
                    f"received {len(embedding)}."
                )

            prepared_chunks.append(
                {
                    "chunk_index": index,
                    "content": chunk,
                    "embedding": embedding,
                }
            )

        # -----------------------------------------------------
        # 6. Save chunks and activate the version transactionally.
        # -----------------------------------------------------
        with SessionLocal.begin() as db:
            current_version = db.scalar(
                select(DocumentVersion)
                .where(DocumentVersion.id == version_id)
                .with_for_update()
            )

            if current_version is None:
                raise ValueError(
                    f"Document version {version_id} no longer exists."
                )

            if current_version.is_active:
                raise ValueError(
                    "This version was activated by another process."
                )

            if current_version.status == "superseded":
                raise ValueError(
                    "This version was superseded by another version."
                )

            current_document = db.scalar(
                select(Document)
                .where(Document.id == document_id)
                .with_for_update()
            )

            if current_document is None:
                raise ValueError(
                    "The parent document no longer exists."
                )

            # Ensure metadata has not changed since processing began.
            if (
                current_version.file_path != version_file_path
                or current_version.product_id != version_product_id
                or current_version.category != version_category
            ):
                raise ValueError(
                    "Version metadata changed during processing. "
                    "Please retry ingestion."
                )

            # Remove chunks from an earlier failed processing attempt.
            db.query(DocumentChunk).filter(
                DocumentChunk.version_id == version_id
            ).delete(synchronize_session=False)

            # Store chunks using this version's own metadata.
            for item in prepared_chunks:
                db.add(
                    DocumentChunk(
                        version_id=version_id,
                        chunk_index=item["chunk_index"],
                        content=item["content"],
                        embedding=item["embedding"],
                        product_id=version_product_id,
                        category=version_category,
                    )
                )

            db.flush()

            # Activate only after all chunks have been saved.
            # This also handles superseding conflicting versions.
            activate_version_and_supersede_conflicts(
                db,
                version_id,
            )

        return len(prepared_chunks)

    except Exception as exc:
        # -----------------------------------------------------
        # 7. Record failure without deactivating an active version.
        # -----------------------------------------------------
        with SessionLocal.begin() as db:
            failed_version = db.scalar(
                select(DocumentVersion)
                .where(DocumentVersion.id == version_id)
                .with_for_update()
            )

            if (
                failed_version is not None
                and not failed_version.is_active
            ):
                failed_version.status = "failed"
                failed_version.error_message = str(exc)[:4000]

        raise
