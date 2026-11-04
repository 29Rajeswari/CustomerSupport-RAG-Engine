
from sqlalchemy import select

from app.db.models import Document, DocumentVersion, DocumentChunk
from app.db.session import SessionLocal
from app.ingestion.processor import process_document_version


def main():
    with SessionLocal() as db:
        rows = db.execute(
            select(DocumentVersion.id, Document.id, Document.title)
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(DocumentVersion.status == "processing")
            .order_by(DocumentVersion.id)
        ).all()

    if not rows:
        print("No versions are stuck in processing.")
        return

    print(f"Found {len(rows)} versions to inspect.")

    for version_id, document_id, title in rows:
        print(
            f"\nProcessing version {version_id} "
            f"(document {document_id}: {title})"
        )

        try:
            process_document_version(version_id)

            with SessionLocal() as db:
                version = db.get(DocumentVersion, version_id)

                chunk_count = db.scalar(
                    select(DocumentChunk.id)
                    .where(DocumentChunk.version_id == version_id)
                    .limit(1)
                )

                print("Status:", version.status if version else "missing")
                print(
                    "Has chunks:",
                    chunk_count is not None,
                )
                print(
                    "Error:",
                    version.error_message if version else "missing",
                )

        except Exception as exc:
            print("Retry failed:", str(exc))


if __name__ == "__main__":
    main()
