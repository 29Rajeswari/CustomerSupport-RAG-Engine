
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_admin

from app.db.models import Document, DocumentVersion, DocumentChunk
from app.db.session import get_db

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.get("/history")
def list_document_history(
    product_id: str | None = None,
    _: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """List documents and their version history, newest uploads first."""

    statement = (
        select(Document, DocumentVersion)
        .join(
            DocumentVersion,
            DocumentVersion.document_id == Document.id,
        )
        .order_by(DocumentVersion.created_at.desc())
    )

    if product_id:
        statement = statement.where(Document.product_id == product_id)

    rows = db.execute(statement).all()

    history = []

    for document, version in rows:
        chunk_count = db.scalar(
            select(func.count(DocumentChunk.id)).where(
                DocumentChunk.version_id == version.id
            )
        )

        history.append(
            {
                "document_id": document.id,
                "title": document.title,
                "category": document.category,
                "product_id": document.product_id,
                "document_status": document.status,
                "file_path": document.file_path,
                "version_id": version.id,
                "version_number": version.version_number,
                "version_status": version.status,
                "is_active": version.is_active,
                "uploaded_at": version.created_at,
                "effective_from": version.effective_from,
                "effective_until": version.effective_until,
                "error_message": version.error_message,
                "chunk_count": chunk_count,
            }
        )

    return {
        "count": len(history),
        "documents": history,
    }


@router.get("/{document_id}/history")
def get_document_version_history(
    document_id: int,
    _: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Return all versions belonging to one document."""

    document = db.get(Document, document_id)

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Document not found.",
        )

    versions = db.scalars(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document_id)
        .order_by(DocumentVersion.version_number.desc())
    ).all()

    result = []

    for version in versions:
        chunk_count = db.scalar(
            select(func.count(DocumentChunk.id)).where(
                DocumentChunk.version_id == version.id
            )
        )

        result.append(
            {
                "version_id": version.id,
                "version_number": version.version_number,
                "status": version.status,
                "is_active": version.is_active,
                "uploaded_at": version.created_at,
                "effective_from": version.effective_from,
                "effective_until": version.effective_until,
                "error_message": version.error_message,
                "chunk_count": chunk_count,
            }
        )

    return {
        "document_id": document.id,
        "title": document.title,
        "category": document.category,
        "product_id": document.product_id,
        "versions": result,
    }
