
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Document, DocumentChunk, DocumentVersion
from app.llm.ollama_client import generate_embedding


def _normalize_category(category: str | None) -> str | None:
    """Normalize category names for consistent filtering."""
    if category is None:
        return None

    normalized = category.strip().casefold()

    if normalized == "warrenty":
        return "warranty"

    return normalized


def search_relevant_chunks(
    db: Session,
    question: str,
    top_k: int | None = None,
    product_id: str | None = None,
    category: str | None = None,
) -> list[dict]:
    """
    Search semantically relevant chunks from active document versions.

    Optional filters:
    - product_id: Restrict results to a specific product.
    - category: Restrict results to a normalized document category.

    Only active documents and active document versions are searched.
    """

    # 1. Validate the question.
    if not question or not question.strip():
        raise ValueError("Question cannot be empty.")

    # 2. Validate the result limit.
    limit = top_k if top_k is not None else settings.TOP_K

    if limit < 1:
        raise ValueError("top_k must be at least 1.")

    # 3. Normalize and validate the product ID.
    normalized_product_id = (
        product_id.strip() if product_id is not None else None
    )

    if product_id is not None and not normalized_product_id:
        raise ValueError("Product ID cannot be empty.")

    # 4. Normalize and validate the category.
    normalized_category = _normalize_category(category)

    if category is not None and not normalized_category:
        raise ValueError("Category cannot be empty.")

    # 5. Generate the question embedding.
    query_embedding = generate_embedding(question.strip())

    distance = DocumentChunk.embedding.cosine_distance(
        query_embedding
    )

    # 6. Find the highest active version number for each document.
    latest_active_version = (
        select(func.max(DocumentVersion.version_number))
        .where(
            DocumentVersion.document_id == Document.id,
            DocumentVersion.is_active.is_(True),
            DocumentVersion.status == "active",
        )
        .correlate(Document)
        .scalar_subquery()
    )

    # 7. Build the semantic search query.
    statement = (
        select(
            Document.id.label("document_id"),
            Document.title.label("document_title"),
            Document.category.label("document_category"),
            DocumentChunk.id.label("chunk_id"),
            DocumentChunk.content.label("content"),
            DocumentChunk.product_id.label("product_id"),
            DocumentChunk.category.label("category"),
            DocumentVersion.id.label("version_id"),
            DocumentVersion.version_number.label("version_number"),
            distance.label("distance"),
        )
        .join(
            DocumentVersion,
            DocumentVersion.document_id == Document.id,
        )
        .join(
            DocumentChunk,
            DocumentChunk.version_id == DocumentVersion.id,
        )
        .where(
            Document.status == "active",
            DocumentVersion.is_active.is_(True),
            DocumentVersion.status == "active",
            DocumentVersion.version_number == latest_active_version,
            DocumentChunk.embedding.is_not(None),
        )
    )

    # 8. Filter by product ID when supplied.
    if normalized_product_id is not None:
        statement = statement.where(
            Document.product_id == normalized_product_id,
            DocumentChunk.product_id == normalized_product_id,
        )

    # 9. Filter by category when supplied.
    if normalized_category is not None:
        if normalized_category == "warranty":
            category_aliases = ["warranty", "warrenty"]
        else:
            category_aliases = [normalized_category]

        statement = statement.where(
            func.lower(func.trim(Document.category)).in_(category_aliases),
            func.lower(func.trim(DocumentChunk.category)).in_(category_aliases),
        )

    # 10. Retrieve the closest matching chunks.
    rows = (
        db.execute(
            statement
            .order_by(distance.asc())
            .limit(limit)
        )
        .all()
    )

    # 11. Return the results with source metadata.
    return [
        {
            "document_id": row.document_id,
            "document_title": row.document_title,
            "document_category": row.document_category,
            "chunk_id": row.chunk_id,
            "content": row.content,
            "product_id": row.product_id,
            "category": row.category,
            "version_id": row.version_id,
            "version_number": row.version_number,
            "distance": float(row.distance),
        }
        for row in rows
    ]
