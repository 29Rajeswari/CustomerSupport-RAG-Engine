# app/services/answer_service.py

import re
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from app.llm.ollama_client import generate_answer
from app.retrieval.search import search_relevant_chunks
from app.services.order_data_service import (
    get_customer_order_by_number,
    get_customer_orders,
)
from app.services.product_data_service import search_products

SYSTEM_PROMPT = """
You are an Indian e-commerce customer support assistant.

You receive information from:
1. Live database records for products, orders and shipments.
2. Retrieved policy documents for warranty, returns, refunds and exchanges.

Rules:
- Use only the supplied live database information and retrieved document evidence.
- Live database information is authoritative for current prices, stock, orders and shipments.
- Policy documents are authoritative for policy conditions.
- Never invent prices, stock quantities, order details, tracking numbers or delivery dates.
- Never combine information from different orders.
- Never claim warranty, refund, replacement or repair eligibility without evidence.
- If policy evidence is insufficient, clearly say so.
- If a document is sample, fictional or unofficial, identify it as sample information.
- Do not expose internal database IDs or other customers' private information.
- If requested information is unavailable, say that it could not be verified.
- Use simple, polite language.
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
    "Important: This answer is based on fictional or sample data used for "
    "testing, not verified official product policy. Please confirm the actual "
    "warranty with the manufacturer or authorized seller."
)


def contains_sample_warning(content: str) -> bool:
    """Return True when retrieved policy content is marked as sample data."""
    normalized = content.casefold()
    return any(marker in normalized for marker in SAMPLE_DOCUMENT_MARKERS)


def detect_category(question: str) -> str | None:
    """Detect policy categories. Product categories are handled separately."""
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
            "delivery",
            "shipping",
            "arrive",
            "arrival",
            "track my order",
            "track order",
            "track my shipment",
            "track shipment",
            "shipment tracking",
            "shipping status",
            "delivery status",
            "where is my shipment",
            "when will my order",
            "when is my order",
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
    """Identify questions about the authenticated customer's orders."""
    text = question.casefold()

    if re.search(r"\bORD-[A-Z0-9]+\b", question.upper()):
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
        "track my product",
        "track my products",
        "track product",
        "track products",
        "tracking my product",
        "tracking my products",
    )

    if any(keyword in text for keyword in order_keywords):
        return True

    # Also recognise product-specific tracking questions such as:
    # "Track my Wireless Earbuds" or "Where is the Redmi Smartphone?"
    tracking_pattern = (
        r"\b(track|tracking|where is|check|status of)\b"
        r".*\b(my|the)\b"
    )
    return bool(re.search(tracking_pattern, text))


def is_product_request(
    question: str,
    product_id: str | None = None,
) -> bool:
    """Identify product catalogue, price and availability questions."""
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
        "product",
        "products",
        "show",
        "list",
        "smartphone",
        "smartphones",
        "mobile",
        "mobiles",
        "phone",
        "phones",
        "laptop",
        "laptops",
        "earbuds",
        "headphones",
        "accessories",
        "oneplus",
        "samsung",
        "redmi",
        "vivo",
        "dell",
        "hp",
    )

    return any(
        re.search(rf"\b{re.escape(keyword)}\b", text) for keyword in product_keywords
    )


def extract_order_number(question: str) -> str | None:
    """Extract an order number such as ORD-ABC123."""
    match = re.search(
        r"\bORD-[A-Z0-9]+\b",
        question.upper(),
    )
    return match.group(0) if match else None


def detect_product_category(question: str) -> str | None:
    """Map customer product terms to database categories."""
    text = question.casefold()

    category_mapping = {
        "Mobiles": (
            "mobile",
            "mobiles",
            "smartphone",
            "smartphones",
            "phone",
            "phones",
        ),
        "Laptops": (
            "laptop",
            "laptops",
        ),
        "Accessories": (
            "accessory",
            "accessories",
            "earbuds",
            "headphones",
        ),
    }

    for category, keywords in category_mapping.items():
        if any(re.search(rf"\b{re.escape(keyword)}\b", text) for keyword in keywords):
            return category

    return None


def extract_product_query(
    question: str,
    product_id: str | None = None,
) -> str | None:
    """Extract a product name or return None for category-only searches."""

    if product_id:
        return product_id.strip().upper()

    product_code = re.search(
        r"\b[A-Z]{2,}-\d{3,}\b",
        question.upper(),
    )

    if product_code:
        return product_code.group(0)

    text = question.casefold().strip()

    # Remove price conditions.
    text = re.sub(
        r"\b(?:under|below|less than|within)\s+"
        r"(?:₹|rs\.?\s*)?\d+(?:,\d{3})*(?:\.\d+)?"
        r"\s*(?:rupees|rs\.?)?",
        " ",
        text,
    )

    text = re.sub(
        r"\bmaximum\s+(?:price\s+)?(?:of\s+)?"
        r"(?:₹|rs\.?\s*)?\d+(?:,\d{3})*(?:\.\d+)?",
        " ",
        text,
    )

    remove_phrases = (
        r"\bshow me\b",
        r"\bshow\b",
        r"\blist\b",
        r"\bfind\b",
        r"\bsearch for\b",
        r"\btell me about\b",
        r"\bdetails about\b",
        r"\bdetails of\b",
        r"\bdo you have\b",
        r"\bis there\b",
        r"\bwhat is\b",
        r"\bwhat are\b",
        r"\bwhich\b",
        r"\bcan\b",
        r"\bcould\b",
        r"\bplease\b",
        r"\bavailable\b",
        r"\bin stock\b",
        r"\bstock\b",
        r"\bprice\b",
        r"\bcost\b",
        r"\bproduct\b",
        r"\bproducts\b",
        r"\ball\b",
        r"\bthe\b",
        r"\bin\b",
        r"\byour\b",
        r"\bour\b",
        r"\bstore\b",
        r"\bany\b",
        r"\bme\b",
        r"\bwant\b",
        r"\bi\b",
        r"\byou\b",
        r"\bto buy\b",
        r"\brupees\b",
    )

    for phrase in remove_phrases:
        text = re.sub(phrase, " ", text)

    text = re.sub(r"[^\w\s-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    # Category-only searches should use the category filter,
    # not the product-name search.
    category_terms = {
        "mobile",
        "mobiles",
        "phone",
        "phones",
        "smartphone",
        "smartphones",
        "laptop",
        "laptops",
        "accessory",
        "accessories",
    }

    if text in category_terms:
        return None

    return text or None


def extract_max_price(question: str) -> Decimal | None:
    """Extract a maximum price from common customer question formats."""
    text = question.casefold().replace(",", "")

    patterns = (
        r"\bunder\s+(?:₹|rs\.?\s*)?(\d+(?:\.\d+)?)",
        r"\bbelow\s+(?:₹|rs\.?\s*)?(\d+(?:\.\d+)?)",
        r"\bless than\s+(?:₹|rs\.?\s*)?(\d+(?:\.\d+)?)",
        r"\bwithin\s+(?:₹|rs\.?\s*)?(\d+(?:\.\d+)?)",
        r"\bmaximum\s+(?:price\s+)?(?:of\s+)?"
        r"(?:₹|rs\.?\s*)?(\d+(?:\.\d+)?)",
    )

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            try:
                return Decimal(match.group(1))
            except InvalidOperation:
                return None

    return None


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


def filter_orders_by_mentioned_product(
    orders: list[dict],
    question: str,
) -> list[dict]:
    """
    Filter orders by a complete purchased product name mentioned in the
    customer's question. If no product name matches, preserve the original
    order list so a general order question can ask the customer to choose.
    """
    normalized_question = question.casefold()

    matching_orders = [
        order
        for order in orders
        if any(
            item.get("product_name", "").casefold() in normalized_question
            for item in order.get("items", [])
            if item.get("product_name")
        )
    ]

    return matching_orders if matching_orders else orders


def format_product_results(products: list[dict]) -> str:
    """Format database product records without asking the LLM to invent details."""
    lines = []

    for product in products:
        availability = "In stock" if product["in_stock"] else "Out of stock"

        lines.append(
            f"Product: {product['product_name']}\n"
            f"Product ID: {product['product_id']}\n"
            f"Category: {product['category']}\n"
            f"Price: ₹{product['price']}\n"
            f"Available quantity: {product['stock_quantity']}\n"
            f"Availability: {availability}"
        )

    return (
        "Here is the latest product information from our inventory:\n\n"
        + "\n\n".join(lines)
    )


def _format_inr(value) -> str:
    """Format a database amount as Indian Rupees without changing its value."""
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return f"₹{value}"

    if amount == amount.to_integral_value():
        return f"₹{int(amount):,}"
    return f"₹{amount:,.2f}"


def _format_order_date(value) -> str | None:
    """Format an ISO date/datetime from the database for customer display."""
    if not value:
        return None

    from datetime import date, datetime

    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        return value.strftime("%B %d, %Y").replace(" 0", " ")
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return str(value)

    return parsed.strftime("%B %d, %Y").replace(" 0", " ")


def format_customer_order_answer(order: dict, question: str) -> str:
    """
    Build order answers from database values directly.
    The LLM is deliberately bypassed for customer-specific order records.
    """
    order_number = order.get("order_number", "your order")
    order_status = str(order.get("order_status") or "unknown").casefold()
    payment_status = str(order.get("payment_status") or "unknown").casefold()
    items = order.get("items") or []
    shipment = order.get("shipment") or {}
    text = question.casefold()

    asks_for_items = any(
        phrase in text
        for phrase in (
            "what product",
            "which product",
            "products did",
            "items did",
            "what did i buy",
            "what did i purchase",
            "purchased in",
            "bought in",
        )
    )

    lines = [f"Order: {order_number}"]

    if asks_for_items:
        lines.append("Products purchased:")
        if items:
            for item in items:
                name = item.get("product_name") or "Product"
                quantity = item.get("quantity", "Not available")
                unit_price = item.get("unit_price")
                subtotal = item.get("subtotal")

                lines.append(f"- {name}")
                lines.append(f"  Quantity: {quantity}")
                if unit_price is not None:
                    lines.append(f"  Unit price: {_format_inr(unit_price)}")
                if subtotal is not None:
                    lines.append(f"  Subtotal: {_format_inr(subtotal)}")
        else:
            lines.append("Product details are not available for this order.")

        lines.append(f"Order status: {order_status.title()}")
        if payment_status != "unknown":
            lines.append(f"Payment status: {payment_status.title()}")

        total = order.get("total_amount")
        if total is not None:
            total_label = (
                "Total amount paid" if payment_status == "paid" else "Order total"
            )
            lines.append(f"{total_label}: {_format_inr(total)}")

        placed_date = _format_order_date(order.get("created_at"))
        if placed_date:
            lines.append(f"Order date: {placed_date}")

        return "\n".join(lines)

    # Order status is authoritative. Never let a shipment row override
    # a cancelled order's status.
    if order_status == "cancelled":
        lines.append("Order status: Cancelled")
        lines.append("This order is not eligible for shipment tracking.")
        if payment_status != "unknown":
            lines.append(f"Payment status: {payment_status.title()}")
        return "\n".join(lines)

    lines.append(f"Order status: {order_status.title()}")

    courier = shipment.get("courier_name")
    tracking_number = shipment.get("tracking_number")
    shipment_status = str(shipment.get("shipment_status") or "").casefold()

    if courier:
        lines.append(f"Courier: {courier}")
    if tracking_number:
        lines.append(f"Tracking number: {tracking_number}")

    # Do not describe a shipment as delivered unless the order itself
    # is also marked delivered.
    if order_status == "delivered":
        delivered_date = _format_order_date(shipment.get("delivered_at"))
        if delivered_date:
            lines.append(f"Delivery date: {delivered_date}")
        elif shipment_status == "delivered":
            lines.append("Delivery status: Delivered")
    elif shipment_status:
        lines.append(f"Shipment status: {shipment_status.replace('_', ' ').title()}")

    estimated_date = _format_order_date(shipment.get("estimated_delivery"))
    if order_status not in ("delivered", "cancelled") and estimated_date:
        lines.append(f"Estimated delivery: {estimated_date}")

    if payment_status != "unknown":
        lines.append(f"Payment status: {payment_status.title()}")

    return "\n".join(lines)


def answer_customer_question(
    db: Session,
    question: str,
    product_id: str | None = None,
    top_k: int | None = None,
    category: str | None = None,
    customer_id: int | None = None,
) -> dict:
    """
    Combine live PostgreSQL information and RAG evidence to answer
    an authenticated customer's support question.
    """
    if not question or not question.strip():
        raise ValueError("Question cannot be empty.")

    clean_question = question.strip()

    # Handle simple greetings.
    if re.fullmatch(
        r"(hi|hello|hey|good morning|good afternoon|good evening)[!. ]*",
        clean_question,
        flags=re.IGNORECASE,
    ):
        return {
            "answer": (
                "Hello! Welcome to our store. I can help you find products, "
                "check prices and availability, track orders, and answer "
                "warranty and return questions. How can I help you today?"
            ),
            "sources": [],
        }

    selected_category = (
        category.strip()
        if category is not None and category.strip()
        else detect_category(clean_question)
    )

    live_data: list[str] = []
    sources: list[dict] = []
    chunks: list[dict] = []
    products: list[dict] = []

    order_request = is_order_request(clean_question)

    # A tracking request must not also trigger a product catalogue search.
    product_request = (
        is_product_request(clean_question, product_id) and not order_request
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
            # This function checks both the order number and customer ID.
            order = get_customer_order_by_number(
                db=db,
                customer_id=customer_id,
                order_number=order_number,
            )

            if not order:
                return {
                    "answer": (
                        f"I couldn't find order {order_number} in your account. "
                        "Please check the order number."
                    ),
                    "sources": [],
                }

            orders = [order]

        else:
            # Fetch this customer's orders only.
            # The service validates that limit is between 1 and 50.
            orders = get_customer_orders(
                db=db,
                customer_id=customer_id,
                limit=50,
            )

            # If the question names a purchased product, narrow the orders.
            orders = filter_orders_by_mentioned_product(
                orders=orders,
                question=clean_question,
            )

            if len(orders) > 1:
                order_options = []

                for order in orders:
                    product_names = ", ".join(
                        item["product_name"] for item in order.get("items", [])
                    )

                    order_options.append(
                        f"- Order: {order['order_number']} | "
                        f"Status: {order['order_status']} | "
                        f"Products: {product_names}"
                    )

                return {
                    "answer": (
                        "You have multiple matching orders. "
                        "Which order would you like me to check?\n\n"
                        + "\n".join(order_options)
                        + "\n\nPlease provide the order number."
                    ),
                    "sources": [
                        {
                            "source_type": "customer_orders",
                            "order_count": len(orders),
                        }
                    ],
                }

        if orders:
            sources.append(
                {
                    "source_type": "customer_orders",
                    "order_count": len(orders),
                }
            )

            # Exact order-number questions are answered directly from the
            # authenticated customer's database record, not generated by Ollama.
            if order_number:
                return {
                    "answer": format_customer_order_answer(
                        order=orders[0],
                        question=clean_question,
                    ),
                    "sources": sources,
                }

            live_data.append("LIVE CUSTOMER ORDER INFORMATION:\\n" + str(orders))
        else:
            live_data.append(
                "No matching orders were found for the authenticated customer."
            )

    # -----------------------------------------------------
    # 2. LIVE PRODUCT INFORMATION
    # -----------------------------------------------------
    if product_request:
        search_query = extract_product_query(
            clean_question,
            product_id,
        )

        product_category = detect_product_category(clean_question)
        max_price = extract_max_price(clean_question)

        products = search_products(
            db=db,
            query=search_query,
            category=product_category,
            max_price=max_price,
            limit=10,
        )

        # Prefer exact product-name or product-ID matches when available.
        # This prevents a broad partial match such as "Wireless Mouse"
        # from appearing when the customer requested "Wireless Earbuds".
        if search_query and products:
            normalized_query = search_query.casefold()

            exact_matches = [
                product
                for product in products
                if (
                    product["product_name"].casefold() == normalized_query
                    or product["product_id"].casefold() == normalized_query
                )
            ]

            if exact_matches:
                products = exact_matches

        if products:
            live_data.append("LIVE PRODUCT INFORMATION:\n" + str(products))
            sources.append(
                {
                    "source_type": "products",
                    "product_count": len(products),
                }
            )
        else:
            live_data.append(
                "No matching active products were found in the product database."
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

            live_data.append("RETRIEVED POLICY DOCUMENT EVIDENCE:\n" + evidence)

            sources.extend(
                [
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
            )

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
    # 5. RETURN EXACT LIVE PRODUCT INFORMATION
    # -----------------------------------------------------
    if product_request and not policy_request:
        if not products:
            return {
                "answer": (
                    "Sorry, we couldn't find a matching active product "
                    "in our inventory. Please check the product name "
                    "or try another brand or category."
                ),
                "sources": [],
            }

        return {
            "answer": format_product_results(products),
            "sources": sources,
        }

    # -----------------------------------------------------
    # 6. GENERATE GROUNDED ANSWER USING OLLAMA
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
- Do not combine information from different orders.
- Do not invent missing information.
- If the requested information is unavailable, clearly say it could not be verified.
- Do not expose internal customer IDs.
- Keep the response concise and polite.
"""

    answer = generate_answer(
        prompt=prompt,
        system_prompt=SYSTEM_PROMPT,
    )

    # -----------------------------------------------------
    # 7. SAMPLE DOCUMENT WARNING
    # -----------------------------------------------------
    is_sample = any(
        contains_sample_warning(str(chunk.get("content", ""))) for chunk in chunks
    )

    if is_sample and SAMPLE_WARNING.casefold() not in answer.casefold():
        answer = f"{SAMPLE_WARNING}\n\n{answer.strip()}"

    return {
        "answer": answer,
        "sources": sources,
    }
