from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Document
from app.db.session import engine

with Session(engine) as db:
    documents = db.scalars(
        select(Document).order_by(Document.id)
    ).all()

    for document in documents:
        path = Path(document.file_path) if document.file_path else None

        print("-" * 70)
        print("Document ID:", document.id)
        print("Title:", document.title)
        print("File:", path.name if path else None)
        print("File exists:", path.exists() if path else False)
