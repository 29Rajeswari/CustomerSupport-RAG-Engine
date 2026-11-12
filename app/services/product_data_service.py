
import re
from decimal import Decimal

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import Product


def search_products(
    db: Session,
    query: str | None = None,
    category: str | None = None,
    max_price: Decimal | None = None,
    limit: int = 10,
) -> list[dict]:
    """
    Search active products using product name, ID,
    description and category.

    Supports:
    - Product name searches
    - Multiple brand searches using OR
    - Category filtering
    - Maximum price filtering
    """

    if not 1 <= limit <= 50:
        raise ValueError("Limit must be between 1 and 50.")

    statement = db.query(Product).filter(
        Product.is_active.is_(True)
    )

    # Product name or ID search.
    if query:
        search_term = query.strip()

        if not search_term:
            raise ValueError("Search query cannot be empty.")

        search_terms = [
            term.strip()
            for term in re.split(
                r"\s+or\s+",
                search_term,
                flags=re.IGNORECASE,
            )
            if term.strip()
        ]

        search_conditions = []

        for term in search_terms:
            pattern = f"%{term}%"

            search_conditions.extend([
                Product.product_id.ilike(pattern),
                Product.product_name.ilike(pattern),
                Product.description.ilike(pattern),
            ])

        statement = statement.filter(
            or_(*search_conditions)
        )

    # Category filtering.
    if category:
        normalized_category = category.strip()

        if not normalized_category:
            raise ValueError("Category cannot be empty.")

        statement = statement.filter(
            Product.category.ilike(normalized_category)
        )

    # Maximum price filtering.
    if max_price is not None:
        if max_price < 0:
            raise ValueError("Maximum price cannot be negative.")

        statement = statement.filter(
            Product.price <= max_price
        )

    products = (
        statement
        .order_by(Product.product_name.asc())
        .limit(limit)
        .all()
    )

    return [
        {
            "product_id": product.product_id,
            "product_name": product.product_name,
            "description": product.description,
            "category": product.category,
            "price": str(product.price),
            "stock_quantity": product.stock_quantity,
            "in_stock": product.stock_quantity > 0,
        }
        for product in products
    ]


def get_product_by_id(
    db: Session,
    product_id: str,
) -> dict | None:
    """Retrieve one active product using its product ID."""

    if not product_id or not product_id.strip():
        raise ValueError("Product ID cannot be empty.")

    product = (
        db.query(Product)
        .filter(
            Product.product_id == product_id.strip().upper(),
            Product.is_active.is_(True),
        )
        .first()
    )

    if product is None:
        return None

    return {
        "product_id": product.product_id,
        "product_name": product.product_name,
        "description": product.description,
        "category": product.category,
        "price": str(product.price),
        "stock_quantity": product.stock_quantity,
        "in_stock": product.stock_quantity > 0,
    }
