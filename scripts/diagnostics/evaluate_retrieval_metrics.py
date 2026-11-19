from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.evaluation.metrics import (
    precision_at_k,
    recall_at_k,
    mean_reciprocal_rank,
)
from app.llm.ollama_client import generate_embedding
from app.retrieval.search import search_relevant_chunks


# Connect to the backup inspection database only.
inspection_url = settings.DATABASE_URL
from sqlalchemy.engine import make_url

inspection_url = make_url(inspection_url).set(
    database="ecommerce_chatbot_backup_inspect"
)

engine = create_engine(inspection_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)


evaluation_cases = [
    {
        "name": "Warranty question",
        "question": "How long is the warranty for the integration test smartphone?",
        "product_id": "TEST-INGEST-001",
        "category": "warranty",
        "relevant_ids": [36],
    },
    {
        "name": "Return question",
        "question": "How many days do I have to return the integration test smartphone?",
        "product_id": "TEST-INGEST-001",
        "category": "return",
        "relevant_ids": [37],
    },
]


try:
    # Confirm the embedding model returns the expected vector size.
    test_embedding = generate_embedding(
        "How long is the warranty?"
    )
    print(f"Query embedding dimensions: {len(test_embedding)}")

    if len(test_embedding) != 768:
        raise ValueError(
            "Embedding dimension mismatch: expected 768."
        )

    with SessionLocal() as db:
        for case in evaluation_cases:
            print("\n" + "=" * 60)
            print(case["name"])
            print("Question:", case["question"])
            print("Expected relevant chunk IDs:", case["relevant_ids"])

            results = search_relevant_chunks(
                db=db,
                question=case["question"],
                product_id=case["product_id"],
                category=case["category"],
                top_k=3,
            )

            retrieved_ids = [item["chunk_id"] for item in results]

            print("Retrieved chunk IDs:", retrieved_ids)

            for rank, item in enumerate(results, start=1):
                print(
                    f"Rank {rank}: chunk={item['chunk_id']}, "
                    f"distance={item['distance']:.4f}"
                )

            print("Precision@3:", precision_at_k(
                retrieved_ids, case["relevant_ids"], k=3
            ))
            print("Recall@3:", recall_at_k(
                retrieved_ids, case["relevant_ids"], k=3
            ))
            print("MRR:", mean_reciprocal_rank(
                retrieved_ids, case["relevant_ids"]
            ))

finally:
    engine.dispose()
