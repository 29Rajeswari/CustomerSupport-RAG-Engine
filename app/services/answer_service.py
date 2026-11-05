
import re

from sqlalchemy.orm import Session

from app.retrieval.search import search_relevant_chunks
from app.llm.ollama_client import generate_answer
from app.services.product_data_service import search_products
from app.services.order_data_service import (
    get_customer_orders,
    get_customer_order_by_number,
)


SYSTEM_PROMPT = """
You are an Indian e-commerce customer support assistant.

You receive two possible information sources:

1. Live database information:
   Current product prices, stock, customer orders and shipments.

2. Retrieved policy documents:
   Warranty, returns, refunds, exchanges and other policies.

IMPORTANT RULES:

1. Use only the supplied live database information
   and retrieved document evidence.

2. Never invent product prices, stock quantities,
   order details, tracking numbers or delivery dates.

3. Treat live database information as authoritative
   for current product and order details.

4. Treat policy documents as authoritative for
   warranty, returns, refunds and coverage conditions.

5. Never use an old document to override a current
   product price or stock quantity.

6. Never claim customer-specific warranty eligibility
   without verification.

7. Distinguish between manufacturing defects,
   hardware failures, physical damage, water damage
   and unauthorized repairs.

8. Do not assume every battery problem is covered
   or excluded. Follow the supplied policy exactly.

9. If policy evidence is insufficient, clearly say so.

10. Never guarantee a repair, replacement, refund
    or claim approval without verified eligibility.

11. If a document is fictional, sample or unofficial,
    clearly identify it as sample information.

12. 12 months equals one year.
    18 months equals one and a half years.
    24 months equals two years.
    6 months equals half a year.

13. Do not expose internal database IDs or private
    information belonging to other customers.

14. If no matching product or order is found,
    clearly explain that it could not be found.

15. Never make up missing information.

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
    normalized = content.casefold()

    return any(
        marker in normalized
        for marker in SAMPLE_DOCUMENT_MARKERS
    )


def detect_category(question: str) -> str | None:
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
            "delivery policy",
            "shipping policy",
            "delivery charges",
            "delivery rules",
            "delivery time",
            "shipping charges",
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


def is_order_request(question: str) -> bool:
    """Identify questions about a customer's own orders."""

    text = question.casefold()

    order_number = re.search(
        r"\bORD-[A-Z0-9]+\b",
        question.upper(),
    )

    if order_number:
        return True

    order_keywords = (
        "my order",
        "my orders",
        "recent orders",
        "order status",
        "track my order",
        "track order",
        "tracking number",
        "where is my order",
        "where's my order",
        "shipment status",
        "has my order",
        "when will my order",
        "when is my order",
    )

    return any(keyword in text for keyword in order_keywords)


def is_product_request(
    question: str,
    product_id: str | None = None,
) -> bool:
    """Identify product price, availability and stock questions."""

    if product_id:
        return True

    text = question.casefold()

    product_keywords = (
        "price",
        "cost",
        "stock",
        "available",
        "availability",
        "in stock",
        "product details",
        "show products",
        "list products",
        "how much",
    )

    return any(keyword in text for keyword in product_keywords)


def extract_order_number(question: str) -> str | None:
    """Extract an order number such as ORD-ABC123."""

    match = re.search(
        r"\bORD-[A-Z0-9]+\b",
        question.upper(),
    )

    return match.group(0) if match else None


def extract_product_query(
    question: str,
    product_id: str | None = None,
) -> str | None:
    """Remove common question words to isolate a product search."""

    if product_id:
        return product_id.strip().upper()

    product_code = re.search(
        r"\b[A-Z]{2,}-\d{3,}\b",
        question.upper(),
    )

    if product_code:
        return product_code.group(0)

    text = question.strip()

    remove_phrases = (
        r"\bwhat is the price of\b",
        r"\bwhat's the price of\b",
        r"\bhow much is\b",
        r"\bhow much does\b",
        r"\bwhat is the cost of\b",
        r"\bshow me\b",
        r"\btell me about\b",
        r"\bdetails about\b",
        r"\bdetails of\b",
        r"\bdo you have\b",
        r"\bis there\b",
        r"\bis\b",
        r"\bthe\b",
        r"\bproduct\b",
        r"\bavailable\b",
        r"\bin stock\b",
        r"\bstock\b",
        r"\bprice\b",
        r"\bcost\b",
        r"\bplease\b",
        r"\bwhat\b",
        r"\bof\b",
    )

    for phrase in remove_phrases:
        text = re.sub(
            phrase,
            " ",
            text,
            flags=re.IGNORECASE,
        )

    text = re.sub(r"[^\w\s-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text or None


def should_search_policy(
    question: str,
    order_request: bool,
) -> bool:
    """Avoid unnecessary policy retrieval for ordinary tracking questions."""

    category = detect_category(question)

    if category is None:
        return False

    if category == "delivery" and order_request:
        return False

    return True


def answer_customer_question(
    db: Session,
    question: str,
    product_id: str | None = None,
    top_k: int | None = None,
    category: str | None = None,
    customer_id: int | None = None,
) -> dict:
    """
    Combine live PostgreSQL information and RAG evidence
    to answer customer support questions.
    """

    if not question or not question.strip():
        raise ValueError("Question cannot be empty.")

    clean_question = question.strip()

    selected_category = (
        category.strip()
        if category is not None and category.strip()
        else detect_category(clean_question)
    )

    live_data = []
    sources = []
    chunks = []

    order_request = is_order_request(clean_question)
    product_request = is_product_request(
        clean_question,
        product_id,
    )

    # -----------------------------------------------------
    # 1. LIVE CUSTOMER ORDER AND SHIPMENT INFORMATION
    # -----------------------------------------------------

    if order_request:

        if customer_id is None or customer_id <= 0:
            return {
                "answer": (
                    "Please sign in to your customer account "
                    "to access your order information."
                ),
                "sources": [],
            }

        order_number = extract_order_number(clean_question)

        if order_number:
            order = get_customer_order_by_number(
                db=db,
                customer_id=customer_id,
                order_number=order_number,
            )

            orders = [order] if order else []

        else:
            orders = get_customer_orders(
                db=db,
                customer_id=customer_id,
                limit=5,
            )

        if orders:
            live_data.append(
                "LIVE CUSTOMER ORDER INFORMATION:\n"
                + str(orders)
            )

            sources.append({
                "source_type": "customer_orders",
                "order_count": len(orders),
            })

        else:
            live_data.append(
                "No matching orders were found for "
                "the authenticated customer."
            )

    # -----------------------------------------------------
    # 2. LIVE PRODUCT INFORMATION
    # -----------------------------------------------------

    if product_request:

        search_query = extract_product_query(
            clean_question,
            product_id,
        )

        products = search_products(
            db=db,
            query=search_query,
            limit=10,
        )

        if products:
            live_data.append(
                "LIVE PRODUCT INFORMATION:\n"
                + str(products)
            )

            sources.append({
                "source_type": "products",
                "product_count": len(products),
            })

        else:
            live_data.append(
                "No matching active products were found "
                "in the product database."
            )

    # -----------------------------------------------------
    # 3. POLICY DOCUMENT RETRIEVAL
    # -----------------------------------------------------

    policy_request = should_search_policy(
        clean_question,
        order_request,
    )

    if policy_request:

        chunks = search_relevant_chunks(
            db=db,
            question=clean_question,
            product_id=product_id,
            top_k=top_k,
            category=selected_category,
        )

        if chunks:
            evidence = "\n\n".join(
                f"Source {i}:\n"
                f"Document: {chunk['document_title']}\n"
                f"Product ID: {chunk['product_id']}\n"
                f"Category: {chunk['category']}\n"
                f"Version: {chunk['version_number']}\n"
                f"Content: {chunk['content']}"
                for i, chunk in enumerate(chunks, start=1)
            )

            live_data.append(
                "RETRIEVED POLICY DOCUMENT EVIDENCE:\n"
                + evidence
            )

            sources.extend([
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
            ])

    # -----------------------------------------------------
    # 4. HANDLE QUESTIONS WITHOUT A DATA SOURCE
    # -----------------------------------------------------

    if not live_data:
        return {
            "answer": (
                "Sorry, I couldn't find relevant product, order "
                "or policy information to answer your question."
            ),
            "sources": [],
        }

    # -----------------------------------------------------
    # 5. GENERATE GROUNDED ANSWER USING OLLAMA
    # -----------------------------------------------------

    prompt = f"""
Customer question:
{clean_question}

Available information:

{"".join(live_data)}

Instructions:
- Answer the customer's exact question.
- Use live database information for products and orders.
- Use policy documents for policy-related questions.
- Do not invent missing information.
- If the requested information is unavailable,
  clearly explain that it could not be verified.
- Do not expose internal customer IDs.
- Keep the response concise and polite.
"""

    answer = generate_answer(
        prompt=prompt,
        system_prompt=SYSTEM_PROMPT,
    )

    # -----------------------------------------------------
    # 6. SAMPLE DOCUMENT WARNING
    # -----------------------------------------------------

    is_sample = any(
        contains_sample_warning(
            str(chunk.get("content", ""))
        )
        for chunk in chunks
    )

    if (
        is_sample
        and SAMPLE_WARNING.casefold() not in answer.casefold()
    ):
        answer = f"{SAMPLE_WARNING}\n\n{answer.strip()}"

    return {
        "answer": answer,
        "sources": sources,
    }
