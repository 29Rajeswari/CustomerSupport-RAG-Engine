
import hashlib
import re

from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url

from app.config import settings
from app.models import Document, DocumentChunk, DocumentVersion

database_url = make_url(settings.DATABASE_URL).set(
    database="ecommerce_chatbot_backup_inspect"
)

engine = create_engine(database_url, pool_pre_ping=True)


def normalize_content(content):
    return re.sub(r"\s+", " ", content.casefold()).strip()


try:
    with engine.connect() as connection:
        statement = (
            select(
                Document.id.label("document_id"),
                Document.title,
                Document.category.label("document_category"),
                DocumentVersion.id.label("version_id"),
                DocumentVersion.version_number,
                DocumentChunk.id.label("chunk_id"),
                DocumentChunk.content,
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
                DocumentVersion.status == "active",
                DocumentVersion.is_active.is_(True),
                DocumentVersion.product_id == "MOB-1001",
            )
            .order_by(Document.id, DocumentChunk.id)
        )

        rows = connection.execute(statement).mappings().all()

        groups = {}

        print("\nACTIVE WARRANTY CHUNK AUDIT")
        print("=" * 80)

        for row in rows:
            normalized = normalize_content(row["content"])
            content_hash = hashlib.sha256(
                normalized.encode("utf-8")
            ).hexdigest()

            groups.setdefault(content_hash, []).append(row)

        duplicate_count = 0

        for records in groups.values():
            if len(records) > 1:
                duplicate_count += 1

                print("\nDUPLICATE GROUP")
                print("-" * 80)

                for row in records:
                    print(
                        f"Document: {row['document_id']} | "
                        f"Title: {row['title']} | "
                        f"Version: {row['version_number']} | "
                        f"Chunk: {row['chunk_id']}"
                    )

        print("\nAUDIT SUMMARY")
        print(f"Active chunks inspected: {len(rows)}")
        print(f"Duplicate content groups: {duplicate_count}")

finally:
    engine.dispose()
