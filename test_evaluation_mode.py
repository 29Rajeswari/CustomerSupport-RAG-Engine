
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.services.answer_service import answer_customer_question


# Create a separate connection for Phase 2 evaluation.
inspection_url = make_url(settings.DATABASE_URL).set(
    database="ecommerce_chatbot_backup_inspect"
)

evaluation_engine = create_engine(
    inspection_url,
    pool_pre_ping=True,
)

EvaluationSession = sessionmaker(
    bind=evaluation_engine,
    autoflush=False,
    autocommit=False,
)


def main():
    db = EvaluationSession()

    try:
        print("Connected database:", evaluation_engine.url.database)

        result = answer_customer_question(
            db=db,
            question=(
                "How long is the warranty for the integration "
                "test smartphone?"
            ),
            product_id="TEST-INGEST-001",
            category="warranty",
            evaluation_mode=True,
        )

        print("\n========== GENERATED ANSWER ==========")
        print(result["answer"])

        print("\n========== RETRIEVED CONTEXT ==========")
        print(result.get("retrieved_context", "No context returned"))

        print("\n========== RETRIEVED CHUNKS ==========")

        for chunk in result.get("retrieved_chunks", []):
            print(f"Document: {chunk['document_title']}")
            print(f"Version: {chunk['version_number']}")
            print(f"Chunk ID: {chunk['chunk_id']}")
            print(f"Content: {chunk['content']}")
            print("-" * 60)

        if not result.get("retrieved_chunks"):
            print("WARNING: No chunks were retrieved.")

    finally:
        db.close()
        evaluation_engine.dispose()


if __name__ == "__main__":
    main()
