
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url

from app.config import settings
from app.models import Document, DocumentVersion

database_url = make_url(settings.DATABASE_URL).set(
    database="ecommerce_chatbot_backup_inspect"
)

engine = create_engine(database_url, pool_pre_ping=True)

try:
    with engine.connect() as connection:
        statement = (
            select(
                Document.id,
                Document.title,
                Document.category,
                Document.status,
                DocumentVersion.id.label("version_id"),
                DocumentVersion.version_number,
                DocumentVersion.status.label("version_status"),
                DocumentVersion.is_active,
                DocumentVersion.product_id,
            )
            .join(
                DocumentVersion,
                DocumentVersion.document_id == Document.id,
            )
            .where(
                DocumentVersion.product_id == "MOB-1001"
            )
            .order_by(
                Document.id,
                DocumentVersion.version_number,
            )
        )

        rows = connection.execute(statement).mappings().all()

        print("\nMOB-1001 DOCUMENT VERSION AUDIT")
        print("=" * 90)

        for row in rows:
            print(
                f"Document ID: {row['id']} | "
                f"Title: {row['title']} | "
                f"Category: {row['category']} | "
                f"Document Status: {row['status']} | "
                f"Version ID: {row['version_id']} | "
                f"Version: {row['version_number']} | "
                f"Version Status: {row['version_status']} | "
                f"Active: {row['is_active']} | "
                f"Product: {row['product_id']}"
            )

finally:
    engine.dispose()
