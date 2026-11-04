
from sqlalchemy.orm import Session

from app.retrieval.search import search_relevant_chunks
from app.llm.ollama_client import generate_answer


SYSTEM_PROMPT = """
You are an Indian e-commerce customer support assistant.

Answer only using the supplied document evidence.

IMPORTANT RULES:

1. Never invent product details, warranty conditions,
   exclusions, or eligibility rules.

2. Follow the document exactly.
   If the document says battery manufacturing defects
   are covered, never say that batteries are excluded.

3. Distinguish between:
   - Manufacturing defects
   - Hardware failures
   - Physical damage
   - Water damage
   - Unauthorized repairs

4. Do not assume that every battery problem is covered.
   Battery manufacturing defects are covered only when
   the supplied policy explicitly says so.

5. Do not assume that every battery problem is excluded.

6. If the customer describes a problem but does not
   provide enough information to identify its cause,
   explain the applicable policy and say that the cause
   must be checked before confirming eligibility.

7. Do not claim customer-specific warranty eligibility
   without verification.

8. If a document is fictional, sample, or unofficial,
   clearly identify it as sample data.

9. 12 months equals one year.
   18 months equals one and a half years.
   24 months equals two years.
   6 months equals half a year.

10. If evidence is insufficient, say that you cannot
    verify the answer.

11. Never guarantee a repair, replacement, refund,
    or claim approval based only on the existence
    of a warranty.

    Explain the applicable coverage conditions.
    If the cause of the customer's issue is unknown,
    state that inspection is required before confirming
    eligibility.
    
Use simple, polite language.
"""
SAMPLE_DOCUMENT_MARKERS = (
    "fictional",
    "sample document",
    "sample data",
    "testing only",
    "software testing",
    "integration test",
    "not an official",
    "unofficial",
)

SAMPLE_WARNING = (
    "Important: This answer is based on fictional or sample data "
    "used for testing, not verified official product policy. "
    "Please confirm the actual warranty with the manufacturer "
    "or authorized seller."
)


def contains_sample_warning(content: str) -> bool:
    """Detect sample or fictional policy documents."""
    normalized = content.casefold()
    return any(
        marker in normalized
        for marker in SAMPLE_DOCUMENT_MARKERS
    )


def detect_category(question: str) -> str | None:
    """Detect a policy category from customer questions."""

    text = question.casefold()

    category_keywords = {
        "extended_warranty": (
            "extended warranty",
            "extra warranty",
            "additional warranty",
            "warranty scheme",
            "protection plan",
        ),

        "cancellation": (
            "cancel my order",
            "cancel the order",
            "order cancellation",
            "cancel this order",
            "cancel an order",
        ),

        "delivery": (
            "delivery",
            "shipping",
            "dispatch",
            "tracking",
            "arrive",
            "shipment",
            "delivery address",
            "change delivery location",
        ),

        "exchange": (
            "exchange",
            "replace my product",
            "replacement",
        ),

        "return": (
            "return",
            "refund",
            "money back",
        ),

        "warranty": (
            "warranty",
            "warrenty",
            "guarantee",
            "repair coverage",
            "warranty period",
        ),
    }

    for category, keywords in category_keywords.items():
        if any(keyword in text for keyword in keywords):
            return category

    return None

def answer_customer_question(
    db: Session,
    question: str,
    product_id: str | None = None,
    top_k: int | None = None,
    category: str | None = None,
) -> dict:
    """Retrieve active evidence and generate a grounded answer."""

    if not question or not question.strip():
        raise ValueError("Question cannot be empty.")

    # Use an explicit category if provided; otherwise detect it.
    selected_category = (
        category.strip() if category is not None else
        detect_category(question.strip())
    )

    chunks = search_relevant_chunks(
        db=db,
        question=question.strip(),
        product_id=product_id,
        top_k=top_k,
        category=selected_category,
    )

    if not chunks:
        return {
            "answer": (
                "Sorry, I couldn't find relevant information "
                "in the active documents to answer your question."
            ),
            "sources": [],
        }

    evidence = "\n\n".join(
        f"Source {i}:\n"
        f"Document: {chunk['document_title']}\n"
        f"Product ID: {chunk['product_id']}\n"
        f"Category: {chunk['category']}\n"
        f"Version: {chunk['version_number']}\n"
        f"Content: {chunk['content']}"
        for i, chunk in enumerate(chunks, start=1)
    )

    prompt = f"""
Customer question:
{question.strip()}

Retrieved document evidence:
{evidence}

Answer directly and concisely using only the supplied evidence.
Do not describe sample information as verified official policy.
If the evidence does not answer the question, say so.
"""

    answer = generate_answer(
        prompt=prompt,
        system_prompt=SYSTEM_PROMPT,
    )

    is_sample = any(
        contains_sample_warning(str(chunk.get("content", "")))
        for chunk in chunks
    )

    if is_sample and SAMPLE_WARNING.casefold() not in answer.casefold():
        answer = f"{SAMPLE_WARNING}\n\n{answer.strip()}"

    sources = [
        {
            "document_id": chunk["document_id"],
            "document_title": chunk["document_title"],
            "product_id": chunk["product_id"],
            "category": chunk["category"],
            "version_id": chunk["version_id"],
            "version_number": chunk["version_number"],
            "chunk_id": chunk["chunk_id"],
        }
        for chunk in chunks
    ]

    return {
        "answer": answer,
        "sources": sources,
    }
