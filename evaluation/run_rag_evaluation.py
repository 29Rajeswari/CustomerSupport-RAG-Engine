import csv
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.retrieval.search import search_relevant_chunks
from evaluation.rag_evaluation_dataset import EVALUATION_DATASET


TOP_K = 3
OUTPUT_FILE = Path("evaluation/rag_evaluation_results.csv")


def calculate_metrics(retrieved_ids, relevant_ids, k=3):
    """
    Duplicate-aware retrieval metrics.

    relevant_ids represents alternative relevant chunks.
    For example, [11, 13] means either chunk is acceptable.
    """
    retrieved = retrieved_ids[:k]
    relevant_groups = [set(relevant_ids)]

    # Each dataset question currently has one relevant group.
    hits = [
        group
        for group in relevant_groups
        if any(chunk_id in group for chunk_id in retrieved)
    ]

    precision = len(hits) / k
    recall = len(hits) / len(relevant_groups)

    reciprocal_rank = 0.0

    for rank, chunk_id in enumerate(retrieved, start=1):
        if any(chunk_id in group for group in relevant_groups):
            reciprocal_rank = 1.0 / rank
            break

    return precision, recall, reciprocal_rank


def main():
    database_url = make_url(settings.DATABASE_URL).set(
        database="ecommerce_chatbot_backup_inspect"
    )

    engine = create_engine(database_url, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine)

    results_summary = []

    try:
        with SessionLocal() as db:
            for case in EVALUATION_DATASET:
                results = search_relevant_chunks(
                    db=db,
                    question=case["question"],
                    product_id=case["product_id"],
                    category=case["category"],
                    top_k=TOP_K,
                )

                retrieved_ids = [
                    item["chunk_id"] for item in results
                ]

                precision, recall, mrr = calculate_metrics(
                    retrieved_ids,
                    case["relevant_ids"],
                    TOP_K,
                )

                row = {
                    "question_id": case["id"],
                    "category": case["category"],
                    "question": case["question"],
                    "expected_chunks": str(case["relevant_ids"]),
                    "retrieved_chunks": str(retrieved_ids),
                    "precision_at_3": precision,
                    "recall_at_3": recall,
                    "mrr": mrr,
                    "retrieval_success": recall > 0,
                }

                results_summary.append(row)

                print(
                    f"{case['id']} | "
                    f"Retrieved: {retrieved_ids} | "
                    f"P@3: {precision:.3f} | "
                    f"R@3: {recall:.3f} | "
                    f"MRR: {mrr:.3f}"
                )

        total = len(results_summary)

        avg_precision = sum(
            row["precision_at_3"] for row in results_summary
        ) / total

        avg_recall = sum(
            row["recall_at_3"] for row in results_summary
        ) / total

        avg_mrr = sum(
            row["mrr"] for row in results_summary
        ) / total

        successful = sum(
            row["retrieval_success"] for row in results_summary
        )

        print("\n" + "=" * 65)
        print("RAG RETRIEVAL EVALUATION SUMMARY")
        print("=" * 65)
        print("Total questions:", total)
        print("Successful retrievals:", successful)
        print("Failed retrievals:", total - successful)
        print(f"Average Precision@3: {avg_precision:.4f}")
        print(f"Average Recall@3:    {avg_recall:.4f}")
        print(f"Mean Reciprocal Rank: {avg_mrr:.4f}")

        with OUTPUT_FILE.open(
            "w", newline="", encoding="utf-8"
        ) as file:
            writer = csv.DictWriter(
                file,
                fieldnames=results_summary[0].keys(),
            )
            writer.writeheader()
            writer.writerows(results_summary)

        print("\nDetailed results saved to:", OUTPUT_FILE)

    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
