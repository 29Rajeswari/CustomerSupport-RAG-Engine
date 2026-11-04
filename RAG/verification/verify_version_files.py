from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Document, DocumentVersion, DocumentChunk
from app.db.session import engine

CANDIDATE_VERSION_IDS = [12, 17, 21]

with Session(engine) as db:
    for version_id in CANDIDATE_VERSION_IDS:
        version = db.get(DocumentVersion, version_id)
        document = db.get(Document, version.document_id)

        file_path = Path(document.file_path)
        file_text = file_path.read_text(
            encoding="utf-8",
            errors="replace"
        )

        chunks = db.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.version_id == version_id)
            .order_by(DocumentChunk.chunk_index)
        ).all()

        print("\n" + "=" * 65)
        print("Version ID:", version_id)
        print("Document:", document.title)
        print("Version number:", version.version_number)
        print("File exists:", file_path.exists())
        print("File:", file_path.name)
        print("File characters:", len(file_text))
        print("Chunk count:", len(chunks))

        for chunk in chunks:
            sample = chunk.content[:150].strip()
            print("\nChunk:", chunk.chunk_index)
            print("Chunk sample:", repr(sample))
            print(
                "Sample found in file:",
                sample in file_text
            )
