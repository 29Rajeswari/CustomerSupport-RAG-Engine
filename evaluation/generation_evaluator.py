
"""Phase 2 generation evaluator for the customer-support RAG engine.

Evaluates generated answers using an Ollama judge.

Metrics:
- faithfulness
- answer_relevance
- context_relevance
- answer_correctness

The evaluation uses ecommerce_chatbot_backup_inspect and does not
change the application's normal database configuration.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import ollama
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.services.answer_service import answer_customer_question


logger = logging.getLogger(__name__)

JUDGE_MODEL = "qwen2.5:3b"
JUDGE_VERSION = "generation-judge-v1"

SCORE_MIN = 1
SCORE_MAX = 5

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = Path(__file__).resolve().parent / "evaluation_results"

REPORT_PATH = RESULTS_DIR / "generation_evaluation_report.json"
CACHE_PATH = RESULTS_DIR / "generation_judge_cache.json"

METRICS = (
    "faithfulness",
    "answer_relevance",
    "context_relevance",
    "answer_correctness",
)

JUDGE_SYSTEM_PROMPT = """
You are a strict evaluator of an Indian e-commerce RAG customer-support answer.

Evaluate only the supplied:
- Customer question
- Retrieved context
- Generated answer
- Reference answer

Do not introduce outside facts.

Return valid JSON only, using this exact structure:

{
  "faithfulness": {"score": 1, "reason": "brief reason"},
  "answer_relevance": {"score": 1, "reason": "brief reason"},
  "context_relevance": {"score": 1, "reason": "brief reason"},
  "answer_correctness": {"score": 1, "reason": "brief reason"}
}

Each score must be an integer from 1 to 5:

1 = Very poor
2 = Poor
3 = Partial or mixed quality
4 = Good
5 = Excellent

Metric definitions:

1. faithfulness:
Are factual claims in the generated answer supported by retrieved context?
Penalize invented or contradictory claims.
If context is empty, score 1.

2. answer_relevance:
Does the answer directly address the customer's question?

3. context_relevance:
Does the retrieved context contain useful evidence for answering the question?
Evaluate the context itself.

4. answer_correctness:
Does the generated answer agree with the reference answer while respecting
the retrieved context?

Do not reward unsupported claims even if they happen to match the reference.

Be strict.
A warning about sample or test policy data is appropriate and should not
be penalized.

Reasons must be concise and specific.
Do not include Markdown fences.
"""


def _load_json(path: Path, default: Any) -> Any:
    """Load a JSON file, returning a default if it does not exist."""
    if not path.exists():
        return default

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Could not read JSON file %s; starting fresh.", path)
        return default


def _normalise_score(value: Any) -> int:
    """Validate and normalize a judge score to an integer from 1 to 5."""
    if isinstance(value, bool):
        raise ValueError("Boolean values are not valid evaluation scores.")

    try:
        score = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid evaluation score: {value!r}")

    if score < SCORE_MIN or score > SCORE_MAX:
        raise ValueError(f"Score must be between 1 and 5, received {score}.")

    return score


def _cache_key(
    question: str,
    context: str,
    answer: str,
    reference_answer: str,
) -> str:
    """Create a cache key based on all evaluation inputs."""
    payload = {
        "question": question,
        "context": context,
        "answer": answer,
        "reference_answer": reference_answer,
        "judge_model": JUDGE_MODEL,
        "judge_version": JUDGE_VERSION,
    }

    encoded = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
    ).encode("utf-8")

    return hashlib.sha256(encoded).hexdigest()


def _parse_judge_response(content: str) -> dict:
    """Parse and validate the judge's JSON response."""
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")

        if start == -1 or end == -1 or end <= start:
            raise ValueError("Judge did not return valid JSON.")

        data = json.loads(content[start:end + 1])

    validated = {}

    for metric in METRICS:
        if metric not in data:
            raise ValueError(f"Judge response is missing metric: {metric}")

        metric_data = data[metric]

        if not isinstance(metric_data, dict):
            raise ValueError(f"Invalid response structure for {metric}.")

        validated[metric] = {
            "score": _normalise_score(metric_data.get("score")),
            "reason": str(metric_data.get("reason", "")).strip(),
        }

    return validated


def judge_generation(
    client: ollama.Client,
    question: str,
    context: str,
    answer: str,
    reference_answer: str,
    cache: dict,
) -> dict:
    """Evaluate one generated answer using the Ollama judge."""

    key = _cache_key(
        question,
        context,
        answer,
        reference_answer,
    )

    if key in cache:
        logger.info("Using cached judgment for this question.")
        return cache[key]

    user_prompt = f"""
CUSTOMER QUESTION:
{question}

RETRIEVED CONTEXT:
{context}

GENERATED ANSWER:
{answer}

REFERENCE ANSWER:
{reference_answer}

Evaluate the generated answer using all four metrics.
Return JSON only.
"""

    last_error = None

    for attempt in range(1, 3):
        try:
            response = client.chat(
                model=JUDGE_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": JUDGE_SYSTEM_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": user_prompt,
                    },
                ],
                format="json",
                options={
                    "temperature": 0,
                },
            )

            content = response.message.content
            judgment = _parse_judge_response(content)

            cache[key] = judgment
            return judgment

        except Exception as exc:
            last_error = exc
            logger.warning(
                "Judge attempt %s failed: %s",
                attempt,
                exc,
            )

    raise RuntimeError(
        f"Ollama judge failed after two attempts: {last_error}"
    )


def _build_summary(results: list[dict]) -> dict:
    """Calculate average scores and success/failure counts."""

    successful = [
        row for row in results
        if row.get("status") == "success" and row.get("scores")
    ]

    failed = [
        row for row in results
        if row.get("status") != "success"
    ]

    metric_summary = {}

    for metric in METRICS:
        scores = [
            row["scores"][metric]["score"]
            for row in successful
            if metric in row["scores"]
        ]

        if scores:
            average = sum(scores) / len(scores)

            metric_summary[metric] = {
                "average_score": round(average, 3),
                "maximum_score": SCORE_MAX,
                "percentage": round(
                    (average / SCORE_MAX) * 100,
                    2,
                ),
                "evaluated_questions": len(scores),
            }
        else:
            metric_summary[metric] = {
                "average_score": None,
                "maximum_score": SCORE_MAX,
                "percentage": None,
                "evaluated_questions": 0,
            }

    return {
        "total_questions": len(results),
        "successful_questions": len(successful),
        "failed_questions": len(failed),
        "success_rate_percentage": (
            round(len(successful) / len(results) * 100, 2)
            if results else 0
        ),
        "metrics": metric_summary,
        "failed_question_ids": [
            row.get("id") for row in failed
        ],
    }


def run_generation_evaluation(dataset: list[dict]) -> dict:
    """Run Phase 2 generation evaluation for the supplied dataset."""

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # Use a separate inspection database for evaluation.
    inspection_url = make_url(
        settings.DATABASE_URL
    ).set(
        database="ecommerce_chatbot_backup_inspect"
    )

    engine = create_engine(
        inspection_url,
        pool_pre_ping=True,
    )

    EvaluationSession = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
    )

    client = ollama.Client(
        host=settings.OLLAMA_BASE_URL
    )

    cache = _load_json(CACHE_PATH, {})
    results = []

    try:
        # Verify the evaluation database connection.
        with engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")

        logger.info(
            "Connected to evaluation database: %s",
            engine.url.database,
        )

        db = EvaluationSession()

        try:
            for index, item in enumerate(dataset, start=1):
                question_id = item["id"]

                logger.info(
                    "[%s/%s] Evaluating %s",
                    index,
                    len(dataset),
                    question_id,
                )

                row = {
                    "id": question_id,
                    "question": item["question"],
                    "product_id": item.get("product_id"),
                    "category": item.get("category"),
                    "reference_answer": item["reference_answer"],
                    "status": "failed",
                }

                try:
                    generated = answer_customer_question(
                        db=db,
                        question=item["question"],
                        product_id=item.get("product_id"),
                        category=item.get("category"),
                        evaluation_mode=True,
                    )

                    answer = str(
                        generated.get("answer", "")
                    ).strip()

                    context = str(
                        generated.get("retrieved_context", "")
                    ).strip()

                    chunks = generated.get(
                        "retrieved_chunks",
                        [],
                    )

                    row.update({
                        "generated_answer": answer,
                        "retrieved_context": context,
                        "retrieved_chunks": chunks,
                        "sources": generated.get("sources", []),
                    })

                    if not answer:
                        raise ValueError(
                            "The answer service returned an empty answer."
                        )

                    if not context or not chunks:
                        raise ValueError(
                            "No retrieved policy context/chunks. "
                            "Check product ID, category, active document "
                            "version, and inspection database retrieval."
                        )

                    judgment = judge_generation(
                        client=client,
                        question=item["question"],
                        context=context,
                        answer=answer,
                        reference_answer=item["reference_answer"],
                        cache=cache,
                    )

                    row["scores"] = judgment
                    row["status"] = "success"

                except Exception as exc:
                    db.rollback()

                    row["error"] = (
                        f"{type(exc).__name__}: {exc}"
                    )

                    logger.exception(
                        "Evaluation failed for %s",
                        question_id,
                    )

                results.append(row)

                # Save cache after every question.
                CACHE_PATH.write_text(
                    json.dumps(
                        cache,
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )

                if row["status"] == "success":
                    score_text = ", ".join(
                        f"{metric}="
                        f"{row['scores'][metric]['score']}/5"
                        for metric in METRICS
                    )

                    print(
                        f"{question_id}: success | {score_text}"
                    )
                else:
                    print(
                        f"{question_id}: failed | "
                        f"{row.get('error', 'Unknown error')}"
                    )

        finally:
            db.close()

    finally:
        engine.dispose()

    summary = _build_summary(results)

    report = {
        "evaluation_name": "Phase 2 - RAG Generation Evaluation",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "database": "ecommerce_chatbot_backup_inspect",
        "generation_model": settings.OLLAMA_CHAT_MODEL,
        "embedding_model": settings.OLLAMA_EMBEDDING_MODEL,
        "judge_model": JUDGE_MODEL,
        "judge_version": JUDGE_VERSION,
        "score_scale": "1-5; percentage = score / 5 * 100",
        "metric_definitions": {
            "faithfulness": (
                "Factual claims in the answer are supported by retrieved context."
            ),
            "answer_relevance": (
                "The answer directly addresses the customer question."
            ),
            "context_relevance": (
                "Retrieved context is useful for answering the question."
            ),
            "answer_correctness": (
                "The answer agrees with the reference answer and retrieved context."
            ),
        },
        "summary": summary,
        "results": results,
    }

    REPORT_PATH.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\n========== PHASE 2 SUMMARY ==========")
    print(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        )
    )

    print(f"\nReport saved to: {REPORT_PATH}")
    print(f"Judge cache saved to: {CACHE_PATH}")

    return report
