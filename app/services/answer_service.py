# app/services/answer_service.py

import re
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from app.llm.ollama_client import generate_answer
from app.models import Product
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
- Do not assume battery issues are covered or excluded unless policy evidence confirms it.
- Distinguish manufacturing defects, hardware failures, physical damage,
  liquid damage and unauthorized repairs according to the retrieved policy.
- Convert warranty months into years when it helps the customer understand.
- Do not claim that a claim has been approved or that a repair, replacement
  or refund has been completed unless the supplied records confirm it.
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
    "Important: The retrieved information comes from sample, "
    "fictional or testing documents. It has not been verified "
    "as an official store policy."
)


def contains_sample_warning(content: str) -> bool:
    """Return True when retrieved policy content is marked as sample data."""
    normalized = content.casefold()
    return any(marker in normalized for marker in SAMPLE_DOCUMENT_MARKERS)


def detect_category(question: str) -> str | None:
    """Detect the specific policy category in a customer question."""
    text = re.sub(r"\s+", " ", question.casefold()).strip()

    category_keywords = {
        "extended_warranty": (
            "extended warranty",
            "extra warranty",
            "additional warranty",
            "warranty scheme",
            "protection plan",
        ),
        "cancellation": (
            "cancellation",
            "cancel my order",
            "cancel the order",
            "cancel this order",
            "cancel an order",
            "how do i cancel",
            "can i cancel",
            "order cancel",
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
            "arrival",
        ),
        "exchange": (
            "exchange",
            "replacement",
            "replace my product",
        ),
        "refund": (
            "refund",
            "money back",
            "refund policy",
        ),
        "return": (
            "return",
            "return policy",
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
    text = re.sub(r"\s+", " ", question.casefold()).strip()

    if re.search(r"\bORD-[A-Z0-9]+\b", question.upper()):
        return True

    order_patterns = (
        r"\bmy\s+orders?\b",
        r"\b(show|view|check|get|list)\s+my\s+orders?\b",
        r"\b(last|latest|previous|recent|most recent)\s+orders?\b",
        r"\bmy\s+(last|latest|previous|recent|most recent)\s+orders?\b",
        r"\b(order|orders)\s+history\b",
        r"\b(show|view|check|get)\s+my\s+order\s+history\b",
        r"\btrack\s+(my\s+)?orders?\b",
        r"\btracking\s+(number|details|status)\b",
        r"\bwhere\s+is\s+my\s+order\b",
        r"\bwhere's\s+my\s+order\b",
        r"\bshipment\s+status\b",
        r"\bhas\s+my\s+order\b",
        r"\bwhen\s+(will|is)\s+my\s+order\b",
        r"\b(order|purchase)\s+(status|details|tracking)\b",
        r"\bmy\s+(recent|previous|last)\s+purchase\b",
        r"\bshow\s+my\s+previous\s+order\b",
    )

    if any(re.search(pattern, text) for pattern in order_patterns):
        return True

    tracking_pattern = (
        r"\b(track|tracking|where is|check|status of)\b"
        r".*\b(my|the)\b"
    )
    return bool(re.search(tracking_pattern, text))


def is_latest_order_request(question: str) -> bool:
    """Identify requests for the customer's most recent order."""
    text = re.sub(r"\s+", " ", question.casefold()).strip()

    patterns = (
        r"\b(last|latest|previous|most recent)\s+(?:product\s+)?order\b",
        r"\bmy\s+(last|latest|previous|most recent)\s+(?:product\s+)?order\b",
        r"\btrack\s+my\s+(last|latest|previous)\s+order\b",
        r"\bmy\s+(last|latest|previous|most recent)\s+purchase\b",
    )
    return any(re.search(pattern, text) for pattern in patterns)


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
        "cheap",
        "cheaper",
        "cheapest",
        "costly",
        "expensive",
        "stock",
        "stocks",
        "zero stock",
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
    match = re.search(r"\bORD-[A-Z0-9]+\b", question.upper())
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


def detect_stock_filter(question: str) -> bool | None:
    """Return True for in-stock, False for out-of-stock, otherwise None."""
    text = re.sub(r"[\s_-]+", " ", question.casefold()).strip()

    out_of_stock_patterns = (
        r"\bout of stock\b",
        r"\bnot available\b",
        r"\bunavailable\b",
        r"\bno stock\b",
        r"\bzero stocks?\b",
        r"\bproducts? with zero stocks?\b",
    )
    in_stock_patterns = (
        r"\bonly available products?\b",
        r"\bavailable products?\b",
        r"\bonly in stock\b",
        r"\bin stock products?\b",
        r"\bproducts? in stock\b",
    )

    if any(re.search(pattern, text) for pattern in out_of_stock_patterns):
        return False

    if any(re.search(pattern, text) for pattern in in_stock_patterns):
        return True

    return None


def is_product_comparison_request(question: str) -> bool:
    """Identify explicit requests to compare named catalogue products."""
    text = question.casefold()
    return bool(
        re.search(
            r"\b(compare|comparison|difference between|vs|versus)\b",
            text,
        )
    )


def find_products_for_comparison(
    db: Session,
    question: str,
) -> list[dict]:
    """Find active catalogue products explicitly named in a comparison question."""
    catalogue = db.query(Product).filter(Product.is_active.is_(True)).all()

    text = question.casefold()
    matches = []

    for product in catalogue:
        name = (product.product_name or "").strip()
        if not name:
            continue

        brand = name.split()[0]

        full_name_match = bool(
            re.search(
                rf"(?<!\w){re.escape(name.casefold())}(?!\w)",
                text,
            )
        )
        brand_match = bool(
            re.search(
                rf"(?<!\w){re.escape(brand.casefold())}(?!\w)",
                text,
            )
        )

        if full_name_match or brand_match:
            matches.append(
                {
                    "product_id": product.product_id,
                    "product_name": name,
                    "category": product.category,
                    "price": product.price,
                    "stock_quantity": product.stock_quantity,
                    "in_stock": (product.stock_quantity or 0) > 0,
                }
            )

    unique = {}
    for item in matches:
        unique[item["product_id"]] = item

    return list(unique.values())


def format_product_comparison(products: list[dict]) -> str:
    """Format a factual side-by-side comparison from live database values."""
    lines = ["Here is the comparison based on the latest inventory data:"]

    for product in products:
        availability = "In stock" if product["in_stock"] else "Out of stock"

        lines.extend(
            [
                "",
                f"Product: {product['product_name']}",
                f"Product ID: {product['product_id']}",
                f"Category: {product['category']}",
                f"Price: {_format_inr(product['price'])}",
                f"Available quantity: {product['stock_quantity']}",
                f"Availability: {availability}",
            ]
        )

    if len(products) == 2:
        try:
            first_price = Decimal(str(products[0]["price"]))
            second_price = Decimal(str(products[1]["price"]))

            if first_price < second_price:
                lines.extend(
                    ["", f"Lower-priced option: {products[0]['product_name']}"]
                )
            elif second_price < first_price:
                lines.extend(
                    ["", f"Lower-priced option: {products[1]['product_name']}"]
                )
            else:
                lines.extend(["", "Both products have the same price."])

        except (InvalidOperation, TypeError, ValueError):
            pass

    return "\n".join(lines)


def is_multi_product_comparison(
    db: Session,
    question: str,
) -> bool:
    """Treat a named 'A and B' catalogue request as a comparison."""
    if not re.search(r"\band\b", question.casefold()):
        return False

    return len(find_products_for_comparison(db, question)) >= 2


def is_latest_model_request(question: str) -> bool:
    """Identify requests that ask which catalogue model is the newest."""
    text = re.sub(r"\s+", " ", question.casefold()).strip()

    return bool(
        re.search(
            r"\b(latest|lastest|newest|most recent)\b"
            r"(?:\s+\w+){0,2}\s+\b(model|product|products|laptop|laptops|phone|phones|mobile|mobiles)\b"
            r"|\b(latest|lastest|newest)\s+model\b",
            text,
        )
    )


def is_price_ranking_request(question: str) -> str | None:
    """Return ascending/descending for explicit cheapest or most expensive requests."""
    text = question.casefold()

    if re.search(
        r"\b(cheapest|cheaper|cheap|least expensive|lowest price)\b",
        text,
    ):
        return "ascending"

    if re.search(
        r"\b(costly|costlier|expensive|most expensive|highest price)\b",
        text,
    ):
        return "descending"

    return None


def requested_recommendation_categories(question: str) -> set[str]:
    """Identify all product categories explicitly requested in a recommendation."""
    text = question.casefold()
    categories = set()

    if re.search(r"\b(laptop|laptops)\b", text):
        categories.add("Laptops")

    if re.search(
        r"\b(phone|phones|mobile|mobiles|smartphone|smartphones)\b",
        text,
    ):
        categories.add("Mobiles")

    if re.search(
        r"\b(accessor(?:y|ies)|earbuds|headphones|mouse|cable|speaker)\b",
        text,
    ):
        categories.add("Accessories")

    return categories


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
        r"\bbest\b",
        r"\bcheap\b",
        r"\bcheaper\b",
        r"\bcheapest\b",
        r"\bcostly\b",
        r"\bcostlier\b",
        r"\bexpensive\b",
        r"\blatest\b",
        r"\blastest\b",
        r"\bmodel\b",
        r"\btop\b",
        r"\bgood\b",
        r"\brecommended\b",
        r"\brecommend\b",
        r"\bsuggest\b",
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
        r"\bonly\b",
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
            f"Price: {_format_inr(product['price'])}\n"
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


def _order_created_at_sort_key(order: dict) -> float:
    """Return a sortable timestamp; undated orders sort after dated orders."""
    value = order.get("created_at")

    if not value:
        return float("-inf")

    try:
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, date):
            parsed = datetime.combine(value, datetime.min.time())
        else:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)

        return parsed.timestamp()

    except (TypeError, ValueError, OverflowError):
        return float("-inf")


def format_customer_order_answer(
    order: dict,
    question: str,
) -> str:
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


def resolve_product_id(
    db: Session,
    question: str,
    supplied_product_id: str | None = None,
) -> str | None:
    """
    Identify a product from its complete name or a unique brand token.
    Ambiguous matches are never resolved arbitrarily.
    """
    if supplied_product_id:
        product = (
            db.query(Product)
            .filter(
                Product.product_id == supplied_product_id.strip().upper(),
                Product.is_active.is_(True),
            )
            .first()
        )

        return product.product_id if product else None

    normalized_question = question.casefold()

    products = db.query(Product).filter(Product.is_active.is_(True)).all()

    exact_name_matches = [
        product
        for product in products
        if product.product_name
        and re.search(
            rf"(?<!\w){re.escape(product.product_name.casefold())}(?!\w)",
            normalized_question,
        )
    ]

    if exact_name_matches:
        longest_length = max(
            len(product.product_name) for product in exact_name_matches
        )

        best_matches = [
            product
            for product in exact_name_matches
            if len(product.product_name) == longest_length
        ]

        matching_ids = {product.product_id for product in best_matches}

        return best_matches[0].product_id if len(matching_ids) == 1 else None

    brand_matches = []

    for product in products:
        if not product.product_name:
            continue

        brand = product.product_name.split()[0].casefold()

        if len(brand) < 3:
            continue

        if re.search(
            rf"(?<!\w){re.escape(brand)}(?!\w)",
            normalized_question,
        ):
            brand_matches.append(product)

    matching_ids = {product.product_id for product in brand_matches}

    if len(matching_ids) == 1:
        return brand_matches[0].product_id

    return None


def answer_customer_question(
    db: Session,
    question: str,
    product_id: str | None = None,
    top_k: int | None = None,
    category: str | None = None,
    customer_id: int | None = None,
    evaluation_mode: bool = False,
) -> dict:
    """
    Combine live PostgreSQL information and RAG evidence to answer
    an authenticated customer's support question.
    """
    if not question or not question.strip():
        raise ValueError("Question cannot be empty.")

    clean_question = question.strip()

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
    retrieved_context = ""

    order_request = is_order_request(clean_question)

    policy_request = should_search_policy(
        clean_question,
        order_request,
    ) or (
        evaluation_mode
        and (selected_category or "").strip().casefold()
        in {
            "warranty",
            "warrenty",
            "return",
            "returns",
            "refund",
            "exchange",
        }
    )

    product_request = (
        is_product_request(clean_question, product_id)
        and not order_request
        and not policy_request
    )

    price_ranking_intent = is_price_ranking_request(clean_question)

    named_comparison_products = (
        find_products_for_comparison(db, clean_question)
        if price_ranking_intent is not None
        else []
    )

    comparison_request = (
        (
            is_product_comparison_request(clean_question)
            or (
                price_ranking_intent is not None and len(named_comparison_products) >= 2
            )
            or is_multi_product_comparison(db, clean_question)
        )
        and not order_request
        and not policy_request
    )

    resolved_product_id = None

    if policy_request:
        if evaluation_mode and product_id:
            resolved_product_id = product_id.strip().upper()
        else:
            resolved_product_id = resolve_product_id(
                db=db,
                question=clean_question,
                supplied_product_id=product_id,
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
        latest_order_request = is_latest_order_request(clean_question)

        if order_number:
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
            orders = get_customer_orders(
                db=db,
                customer_id=customer_id,
                limit=50,
            )

            orders = filter_orders_by_mentioned_product(
                orders=orders,
                question=clean_question,
            )

            if latest_order_request and orders:
                orders = sorted(
                    orders,
                    key=_order_created_at_sort_key,
                    reverse=True,
                )[:1]

            elif len(orders) > 1:
                order_options = []

                for order in orders:
                    product_names = ", ".join(
                        item.get("product_name", "Product")
                        for item in order.get("items", [])
                    )

                    order_options.append(
                        f"- Order: {order.get('order_number', 'Unavailable')} | "
                        f"Status: {order.get('order_status', 'Unknown')} | "
                        f"Products: {product_names or 'Not available'}"
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

        if not orders:
            if latest_order_request:
                return {
                    "answer": (
                        "I couldn't find a previous order in your account. "
                        "You can check your order history for more information."
                    ),
                    "sources": [],
                }

            return {
                "answer": "I couldn't find any orders in your account.",
                "sources": [],
            }

        sources.append(
            {
                "source_type": "customer_orders",
                "order_count": len(orders),
            }
        )

        if order_number or latest_order_request or len(orders) == 1:
            return {
                "answer": format_customer_order_answer(
                    order=orders[0],
                    question=clean_question,
                ),
                "sources": sources,
            }

        live_data.append("LIVE CUSTOMER ORDER INFORMATION:\n" + str(orders))

    # -----------------------------------------------------
    # 2. LIVE PRODUCT INFORMATION
    # -----------------------------------------------------
    if product_request and comparison_request:
        compared_products = find_products_for_comparison(
            db,
            clean_question,
        )

        if len(compared_products) < 2:
            return {
                "answer": (
                    "I could identify fewer than two active products to compare. "
                    "Please mention two product names or brands from our catalogue."
                ),
                "sources": [],
            }

        if len(compared_products) > 2:
            product_names = ", ".join(
                item["product_name"] for item in compared_products
            )

            return {
                "answer": (
                    "I found more than two matching products: "
                    f"{product_names}. Please specify the two products "
                    "you want to compare."
                ),
                "sources": [
                    {
                        "source_type": "products",
                        "product_count": len(compared_products),
                    }
                ],
            }

        return {
            "answer": format_product_comparison(compared_products),
            "sources": [
                {
                    "source_type": "products",
                    "product_count": len(compared_products),
                }
            ],
        }

    if product_request:
        search_query = extract_product_query(
            clean_question,
            product_id,
        )

        product_category = detect_product_category(clean_question)
        max_price = extract_max_price(clean_question)
        stock_filter = detect_stock_filter(clean_question)
        price_ranking = is_price_ranking_request(clean_question)
        latest_model_request = is_latest_model_request(clean_question)

        recommendation_request = bool(
            re.search(
                r"\b(suggest|recommend|recommendation|best)\b",
                clean_question.casefold(),
            )
        )

        recommendation_categories = requested_recommendation_categories(clean_question)

        if price_ranking or recommendation_request or latest_model_request:
            search_query = None

        if len(recommendation_categories) > 1:
            product_category = None

        products = search_products(
            db=db,
            query=search_query,
            category=product_category,
            max_price=max_price,
            limit=50,
            in_stock=stock_filter,
        )

        if recommendation_categories:
            products = [
                item
                for item in products
                if item.get("category") in recommendation_categories
            ]

        if latest_model_request:
            if products:
                answer = (
                    "I can show the active products in this category, but I cannot "
                    "verify which is the latest model because the product catalogue "
                    "does not currently contain model release dates or model-year data.\n\n"
                    + format_product_results(products)
                )

                return {
                    "answer": answer,
                    "sources": [
                        {
                            "source_type": "products",
                            "product_count": len(products),
                        }
                    ],
                }

            return {
                "answer": (
                    "I couldn't find active products matching that category. "
                    "I also cannot verify the latest model without model release-date "
                    "or model-year information in the catalogue."
                ),
                "sources": [],
            }

        if price_ranking and products:
            products = sorted(
                products,
                key=lambda item: Decimal(str(item.get("price", 0))),
                reverse=(price_ranking == "descending"),
            )

            if re.search(
                r"\b(product|item)\b",
                clean_question.casefold(),
            ):
                best_price = Decimal(str(products[0].get("price", 0)))

                products = [
                    item
                    for item in products
                    if Decimal(str(item.get("price", 0))) == best_price
                ]

        elif recommendation_request and products:
            if recommendation_categories:
                selected = []

                for requested_category in sorted(recommendation_categories):
                    category_products = [
                        item
                        for item in products
                        if item.get("category") == requested_category
                    ]

                    if category_products:
                        selected.append(
                            min(
                                category_products,
                                key=lambda item: Decimal(str(item.get("price", 0))),
                            )
                        )

                products = selected

            else:
                products = sorted(
                    products,
                    key=lambda item: Decimal(str(item.get("price", 0))),
                )[:3]

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
            if stock_filter is False:
                no_products_message = (
                    "There are currently no active products marked as out of stock."
                )
            elif stock_filter is True:
                no_products_message = (
                    "There are currently no active in-stock products matching "
                    "the requested filters."
                )
            else:
                no_products_message = (
                    "No matching active products were found in the product database."
                )

            live_data.append(no_products_message)

    # -----------------------------------------------------
    # 3. POLICY DOCUMENT RETRIEVAL
    # -----------------------------------------------------
    if policy_request:
        text = clean_question.casefold()

        product_specific_pattern = (
            r"\b(for|on)\s+"
            r"(?:the\s+)?"
            r"(?!all\b|general\b|returns?\b|refunds?\b|orders?\b)"
            r"[a-z0-9]"
        )

        is_product_specific = (
            product_id is not None
            or resolved_product_id is not None
            or bool(
                re.search(
                    product_specific_pattern,
                    text,
                )
            )
            or bool(
                re.search(
                    r"\b(my|this|these|purchased|bought)\s+"
                    r"(product|item|device|phone|laptop|earbuds)\b",
                    text,
                )
            )
        )

        if is_product_specific and not resolved_product_id:
            return {
                "answer": (
                    "I couldn't identify the exact product in our "
                    "catalogue. Please provide the complete product "
                    "name or product ID so I can check its policy."
                ),
                "sources": [],
            }

        chunks = search_relevant_chunks(
            db=db,
            question=clean_question,
            product_id=(resolved_product_id if is_product_specific else None),
            top_k=top_k,
            category=selected_category,
            general_only=not is_product_specific,
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

            # Preserve the exact policy evidence supplied to the LLM.
            # It is returned only when evaluation_mode=True.
            retrieved_context = evidence

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

        else:
            return {
                "answer": (
                    f"Sorry, I couldn't find an active "
                    f"{selected_category or 'relevant'} policy document "
                    "in our database. Please contact customer support "
                    "for confirmation."
                ),
                "sources": [],
            }

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
    if product_request and not policy_request and not comparison_request:
        if not products:
            if stock_filter is False:
                answer = (
                    "There are currently no active products marked as out of stock."
                )
            elif stock_filter is True:
                answer = (
                    "There are currently no active in-stock products matching "
                    "your requested filters."
                )
            else:
                answer = (
                    "Sorry, we couldn't find a matching active product "
                    "in our inventory. Please check the product name "
                    "or try another brand or category."
                )

            return {
                "answer": answer,
                "sources": [],
            }

        answer = format_product_results(products)

        if recommendation_request and re.search(r"\bbest\b", clean_question.casefold()):
            answer = (
                "These suggestions are selected using the lowest available prices. "
                "The catalogue does not currently contain customer ratings or review "
                "scores, so I cannot verify which products are objectively the best.\n\n"
                + answer
            )

        return {
            "answer": answer,
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

    result = {
        "answer": answer,
        "sources": sources,
    }

    if evaluation_mode:
        result["retrieved_context"] = retrieved_context
        result["retrieved_chunks"] = [
            {
                "document_id": chunk["document_id"],
                "document_title": chunk["document_title"],
                "product_id": chunk["product_id"],
                "category": chunk["category"],
                "version_id": chunk["version_id"],
                "version_number": chunk["version_number"],
                "chunk_id": chunk["chunk_id"],
                "content": chunk["content"],
            }
            for chunk in chunks
        ]

    return result
