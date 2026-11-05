
from decimal import Decimal

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.models import Product


def search_products(
    db: Session,
    query: str | None = None,
    category: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """
    Search active products using product name, ID,
    description or category.

    Returns live product information from PostgreSQL.
    """

    if not 1 <= limit <= 50:
        raise ValueError("Limit must be between 1 and 50.")

    statement = db.query(Product).filter(
        Product.is_active.is_(True)
    )

    if query:
        search_term = query.strip()

        if not search_term:
            raise ValueError("Search query cannot be empty.")

        pattern = f"%{search_term}%"

        statement = statement.filter(
            or_(
                Product.product_id.ilike(pattern),
                Product.product_name.ilike(pattern),
                Product.description.ilike(pattern),
            )
        )

    if category:
        normalized_category = category.strip()

        if not normalized_category:
            raise ValueError("Category cannot be empty.")

        statement = statement.filter(
            Product.category.ilike(normalized_category)
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
