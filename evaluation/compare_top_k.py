
import io
import json
import math
from contextlib import redirect_stdout
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.retrieval.search import search_relevant_chunks

from evaluation.rag_evaluation_dataset import EVALUATION_DATASET
from evaluation.automatic_relevance_judge import (
    RESULT_DIR,
    get_eligible_chunks,
    judge_all_chunks,
    normalize_and_hash,
)


# ==================================================
# CONFIGURATION
# ==================================================

TOP_K = 5

REPORT_FILE = RESULT_DIR / "rag_evaluation_report.json"


# ==================================================
# DATABASE CONNECTION
# ==================================================

def create_inspection_session():

    database_url = make_url(
        settings.DATABASE_URL
    ).set(
        database="ecommerce_chatbot_backup_inspect"
    )

    engine = create_engine(
        database_url,
        pool_pre_ping=True,
    )

    SessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
    )

    return engine, SessionLocal


# ==================================================
# METRIC CALCULATIONS
# ==================================================

def calculate_dcg(relevance_scores):
    """Calculate Discounted Cumulative Gain."""

    return sum(
        score / math.log2(rank + 1)
        for rank, score in enumerate(
            relevance_scores,
            start=1,
        )
    )


def calculate_question_metrics(
    retrieved_results,
    judgments,
    k=TOP_K,
):
    """
    Calculate content-deduplicated retrieval metrics.

    Precision@K:
        Unique relevant retrieved contents / K

    Recall@K:
        Unique relevant retrieved contents /
        Total unique relevant eligible contents

    MRR@K:
        Reciprocal rank of first relevant unique result

    nDCG@K:
        Ranking quality using binary relevance.

    Hit@K:
        1 if at least one relevant result is retrieved.
    """

    top_results = retrieved_results[:k]

    # Deduplicate retrieved content while preserving rank.
    unique_retrieved = []
    seen_hashes = set()

    for result in top_results:

        content_hash = normalize_and_hash(
            result["content"]
        )

        if content_hash in seen_hashes:
            continue

        seen_hashes.add(content_hash)

        unique_retrieved.append({
            "content_hash": content_hash,
            "chunk_id": result["chunk_id"],
        })

    # Unique relevant eligible contents.
    relevant_hashes = {
        content_hash
        for content_hash, judgment in judgments.items()
        if judgment["relevant"]
    }

    retrieved_hashes = {
        item["content_hash"]
        for item in unique_retrieved
    }

    matched_hashes = (
        retrieved_hashes & relevant_hashes
    )

    # Precision@K
    precision = (
        len(matched_hashes) / k
        if k > 0
        else 0.0
    )

    # Recall@K
    if relevant_hashes:

        recall = (
            len(matched_hashes)
            / len(relevant_hashes)
        )

    else:
        recall = None

    # MRR@K
    reciprocal_rank = 0.0

    for rank, item in enumerate(
        unique_retrieved,
        start=1,
    ):

        if item["content_hash"] in relevant_hashes:

            reciprocal_rank = 1.0 / rank
            break

    # nDCG@K
    actual_scores = [
        1 if item["content_hash"] in relevant_hashes else 0
        for item in unique_retrieved
    ]

    ideal_scores = [
        1
    ] * min(len(relevant_hashes), k)

    dcg = calculate_dcg(actual_scores)
    idcg = calculate_dcg(ideal_scores)

    ndcg = (
        dcg / idcg
        if idcg > 0
        else 0.0
    )

    # Hit@K
    hit = 1 if matched_hashes else 0

    metrics = {
        "precision": precision,
        "recall": recall,
        "mrr": reciprocal_rank,
        "ndcg": ndcg,
        "hit": hit,
    }

    counts = {
        "eligible_unique_contents": len(judgments),
        "relevant_eligible_contents": len(relevant_hashes),
        "retrieved_results": len(top_results),
        "retrieved_unique_contents": len(unique_retrieved),
        "matched_unique_contents": len(matched_hashes),
    }

    return metrics, counts


# ==================================================
# BUILD ELIGIBLE CHUNK DIAGNOSTICS
# ==================================================

def build_eligible_diagnostics(
    eligible_chunks,
    judgments,
):
    """
    Include every eligible chunk and its Qwen judgment.

    Duplicate contents remain visible here, but share
    the same content hash and judgment.
    """

    diagnostics = []

    for chunk in eligible_chunks:

        content_hash = normalize_and_hash(
            chunk["content"]
        )

        judgment = judgments.get(content_hash)

        diagnostics.append({
            "document_id": chunk["document_id"],
            "document_title": chunk["document_title"],
            "document_category": chunk["document_category"],
            "chunk_id": chunk["chunk_id"],
            "product_id": chunk["product_id"],
            "category": chunk["category"],
            "version_id": chunk["version_id"],
            "version_number": chunk["version_number"],
            "content_hash": content_hash,
            "content": chunk["content"],
            "judgment": judgment,
        })

    return diagnostics


# ==================================================
# BUILD RETRIEVED TOP-K DIAGNOSTICS
# ==================================================

def build_retrieval_diagnostics(
    retrieved_results,
    judgments,
    k=TOP_K,
):
    """
    Store the actual retrieved results in their original
    retrieval order, including duplicate contents.
    """

    diagnostics = []

    for rank, result in enumerate(
        retrieved_results[:k],
        start=1,
    ):

        content_hash = normalize_and_hash(
            result["content"]
        )

        judgment = judgments.get(content_hash)

        item = {
            "rank": rank,
            "chunk_id": result["chunk_id"],
            "content_hash": content_hash,
            "content": result["content"],
            "judgment": judgment,
        }

        # Preserve an available retrieval score without
        # assuming a particular score field exists.
        for score_field in (
            "score",
            "similarity",
            "similarity_score",
            "distance",
        ):

            if score_field in result:

                item["retrieval_score"] = {
                    "field": score_field,
                    "value": result[score_field],
                }

                break

        diagnostics.append(item)

    return diagnostics


# ==================================================
# EVALUATION
# ==================================================

def run_evaluation():

    engine, SessionLocal = create_inspection_session()

    db = SessionLocal()

    all_results = {
        "evaluation_type": (
            "Automatic LLM-judged, "
            "content-deduplicated RAG evaluation"
        ),
        "judge_model": "qwen2.5:3b",
        "judge_version": "v3",
        "top_k": TOP_K,
        "total_questions": len(EVALUATION_DATASET),
        "generated_at": (
            datetime.now().astimezone().isoformat()
        ),
        "individual_questions": {},
    }

    try:

        print("\n" + "=" * 65)
        print("INDIVIDUAL QUESTION EVALUATION METRICS")
        print(f"RETRIEVAL: TOP-{TOP_K}")
        print("=" * 65)

        # ==============================================
        # PROCESS EACH QUESTION SEPARATELY
        # ==============================================

        for case in EVALUATION_DATASET:

            question_id = case["id"]
            question = case["question"]

            product_id = case.get("product_id")
            category = case.get("category")

            # ------------------------------------------
            # STEP 1: GET ELIGIBLE ACTIVE CHUNKS
            # ------------------------------------------

            eligible_chunks = get_eligible_chunks(
                db=db,
                product_id=product_id,
                category=category,
            )

            # ------------------------------------------
            # STEP 2: GET AUTOMATIC QWEN JUDGMENTS
            # ------------------------------------------

            # Suppress detailed output while retaining
            # all judgments for the diagnostic report.
            with redirect_stdout(io.StringIO()):

                judgments = judge_all_chunks(
                    question=question,
                    chunks=eligible_chunks,
                )

            # ------------------------------------------
            # STEP 3: RETRIEVE TOP-K RESULTS
            # ------------------------------------------

            retrieved_results = search_relevant_chunks(
                db=db,
                question=question,
                top_k=TOP_K,
                product_id=product_id,
                category=category,
            )

            # ------------------------------------------
            # STEP 4: CALCULATE METRICS AND COUNTS
            # ------------------------------------------

            metrics, counts = calculate_question_metrics(
                retrieved_results=retrieved_results,
                judgments=judgments,
                k=TOP_K,
            )

            # ------------------------------------------
            # STEP 5: BUILD DIAGNOSTIC INFORMATION
            # ------------------------------------------

            eligible_diagnostics = build_eligible_diagnostics(
                eligible_chunks=eligible_chunks,
                judgments=judgments,
            )

            retrieval_diagnostics = build_retrieval_diagnostics(
                retrieved_results=retrieved_results,
                judgments=judgments,
                k=TOP_K,
            )

            # ------------------------------------------
            # STEP 6: SAVE INDIVIDUAL QUESTION RESULTS
            # ------------------------------------------

            all_results["individual_questions"][question_id] = {

                "question": question,

                "filters": {
                    "product_id": product_id,
                    "category": category,
                },

                "metrics": metrics,

                "counts": counts,

                "diagnostics": {
                    "eligible_chunks": eligible_diagnostics,
                    "retrieved_top_k": retrieval_diagnostics,
                },
            }


        # ==============================================
        # CALCULATE COMBINED METRICS FOR ALL QUESTIONS
        # ==============================================

        question_results = list(
            all_results["individual_questions"].values()
        )

        total_questions = len(question_results)

        precision_values = [
            item["metrics"]["precision"]
            for item in question_results
        ]

        recall_values = [
            item["metrics"]["recall"]
            for item in question_results
            if item["metrics"]["recall"] is not None
        ]

        mrr_values = [
            item["metrics"]["mrr"]
            for item in question_results
        ]

        ndcg_values = [
            item["metrics"]["ndcg"]
            for item in question_results
        ]

        hit_values = [
            item["metrics"]["hit"]
            for item in question_results
        ]

        combined_metrics = {
            "precision_at_5": (
                sum(precision_values) / total_questions
                if total_questions else 0.0
            ),

            "recall_at_5": (
                sum(recall_values) / len(recall_values)
                if recall_values else None
            ),

            "mrr_at_5": (
                sum(mrr_values) / total_questions
                if total_questions else 0.0
            ),

            "ndcg_at_5": (
                sum(ndcg_values) / total_questions
                if total_questions else 0.0
            ),

            "hit_at_5": (
                sum(hit_values) / total_questions
                if total_questions else 0.0
            ),

            "successful_questions": sum(hit_values),

            "failed_questions": total_questions - sum(hit_values),

            "total_questions": total_questions,

            "questions_with_valid_recall": len(recall_values),

            "recall_na_questions": (
                total_questions - len(recall_values)
            ),

            "aggregation_method": "Macro Average",
        }

        all_results["overall_metrics"] = combined_metrics

        # ==============================================
        # PRINT COMBINED METRICS
        # ==============================================

        print("\n" + "=" * 65)
        print("COMBINED RAG EVALUATION METRICS")
        print(f"TOTAL QUESTIONS: {total_questions}")
        print(f"RETRIEVAL: TOP-{TOP_K}")
        print("AGGREGATION: MACRO AVERAGE")
        print("=" * 65)

        print(
            f"Overall Precision@{TOP_K}: "
            f"{combined_metrics['precision_at_5']:.4f}"
        )

        recall_value = combined_metrics["recall_at_5"]

        print(
            f"Overall Recall@{TOP_K}: "
            f"{recall_value:.4f}"
            if recall_value is not None
            else f"Overall Recall@{TOP_K}: N/A"
        )

        print(
            f"Overall MRR@{TOP_K}: "
            f"{combined_metrics['mrr_at_5']:.4f}"
        )

        print(
            f"Overall nDCG@{TOP_K}: "
            f"{combined_metrics['ndcg_at_5']:.4f}"
        )

        print(
            f"Overall Hit@{TOP_K}: "
            f"{combined_metrics['hit_at_5']:.4f}"
        )

        print(
            f"Successful Questions: "
            f"{combined_metrics['successful_questions']}"
        )

        print(
            f"Failed Questions: "
            f"{combined_metrics['failed_questions']}"
        )

        print("=" * 65)


        # ==============================================
        # SAVE COMPLETE JSON REPORT
        # ==============================================

        RESULT_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        with REPORT_FILE.open(
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                all_results,
                file,
                indent=2,
                ensure_ascii=False,
            )

        print("\nEvaluation completed.")
        print(
            f"Questions evaluated: "
            f"{len(EVALUATION_DATASET)}"
        )

        print(f"Report saved to: {REPORT_FILE}")

    finally:

        db.close()
        engine.dispose()


# ==================================================
# ENTRY POINT
# ==================================================

if __name__ == "__main__":
    run_evaluation()
