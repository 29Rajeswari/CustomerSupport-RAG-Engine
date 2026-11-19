from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.retrieval.search import search_relevant_chunks
from evaluation.rag_evaluation_dataset import EVALUATION_DATASET

TOP_K_VALUES = [3, 4, 5]

database_url = make_url(settings.DATABASE_URL).set(
    database="ecommerce_chatbot_backup_inspect"
)

engine = create_engine(database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)

try:
    with SessionLocal() as db:
        for k in TOP_K_VALUES:
            successful = 0

            for case in EVALUATION_DATASET:
                results = search_relevant_chunks(
                    db=db,
                    question=case["question"],
                    product_id=case["product_id"],
                    category=case["category"],
                    top_k=k,
                )

                retrieved_ids = {
                    item["chunk_id"] for item in results
                }

                relevant_ids = set(case["relevant_ids"])

                if retrieved_ids & relevant_ids:
                    successful += 1

            recall = successful / len(EVALUATION_DATASET)

            print(
                f"Top K: {k} | "
                f"Successful: {successful}/25 | "
                f"Recall: {recall:.4f}"
            )

finally:
    engine.dispose()
