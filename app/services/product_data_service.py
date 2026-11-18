#app/services/product_data_service.py

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
    in_stock: bool | None = None,
) -> list[dict]:
    """
    Search active products using product name, ID,
    description, category, price and stock availability.

    Supports:
    - Product name searches
    - Multiple brand searches using OR
    - Category filtering
    - Maximum price filtering
    - In-stock product filtering
    - Out-of-stock product filtering

    Args:
        db: SQLAlchemy database session.
        query: Product name, product ID or search terms.
        category: Product category.
        max_price: Maximum product price.
        limit: Maximum number of products to return.
        in_stock:
            True  = Only products with stock_quantity > 0.
            False = Only products with stock_quantity == 0.
            None  = Return products regardless of stock.
    """

    # Validate result limit.
    if not 1 <= limit <= 50:
        raise ValueError("Limit must be between 1 and 50.")

    # Start with active products.
    statement = db.query(Product).filter(
        Product.is_active.is_(True)
    )

    # -------------------------------------------------
    # 1. STOCK AVAILABILITY FILTER
    # -------------------------------------------------
    if in_stock is True:
        statement = statement.filter(
            Product.stock_quantity > 0
        )

    elif in_stock is False:
        statement = statement.filter(
            Product.stock_quantity == 0
        )

    # -------------------------------------------------
    # 2. PRODUCT NAME OR PRODUCT ID SEARCH
    # -------------------------------------------------
    if query is not None:
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

        if not search_terms:
            raise ValueError("Search query cannot be empty.")

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

    # -------------------------------------------------
    # 3. CATEGORY FILTER
    # -------------------------------------------------
    if category is not None:
        normalized_category = category.strip()

        if not normalized_category:
            raise ValueError("Category cannot be empty.")

        statement = statement.filter(
            Product.category.ilike(normalized_category)
        )

    # -------------------------------------------------
    # 4. MAXIMUM PRICE FILTER
    # -------------------------------------------------
    if max_price is not None:
        if max_price < 0:
            raise ValueError("Maximum price cannot be negative.")

        statement = statement.filter(
            Product.price <= max_price
        )

    # -------------------------------------------------
    # 5. EXECUTE DATABASE QUERY
    # -------------------------------------------------
    products = (
        statement
        .order_by(Product.product_name.asc())
        .limit(limit)
        .all()
    )

    # -------------------------------------------------
    # 6. FORMAT PRODUCT RESULTS
    # -------------------------------------------------
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
    """
    Retrieve one active product using its product ID.
    """

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
