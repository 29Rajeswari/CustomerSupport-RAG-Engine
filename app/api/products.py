
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_admin
from app.db.models import Product
from app.db.session import get_db
from app.schemas.product import (
    ProductCreate,
    ProductListResponse,
    ProductResponse,
    ProductUpdate,
)


router = APIRouter(tags=["Products"])


# ---------------------------------------------------------
# 1. ADD A PRODUCT (ADMIN ONLY)
# ---------------------------------------------------------

@router.post(
    "/admin/products",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_product(
    request: ProductCreate,
    _: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    existing_product = db.query(Product).filter(
        Product.product_id == request.product_id
    ).first()

    if existing_product:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A product with this product ID already exists.",
        )

    product = Product(
        product_id=request.product_id,
        product_name=request.product_name,
        description=request.description,
        category=request.category,
        price=request.price,
        stock_quantity=request.stock_quantity,
        is_active=True,
    )

    try:
        db.add(product)
        db.commit()
        db.refresh(product)

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Product could not be created. Check whether its ID already exists.",
        )

    return product


# ---------------------------------------------------------
# 2. LIST ALL PRODUCTS (ADMIN ONLY)
# ---------------------------------------------------------

@router.get(
    "/admin/products",
    response_model=ProductListResponse,
)
def list_admin_products(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    query = db.query(Product)

    total = query.count()

    products = (
        query
        .order_by(Product.created_at.desc(), Product.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "products": products,
    }


# ---------------------------------------------------------
# 3. UPDATE PRODUCT (ADMIN ONLY)
# ---------------------------------------------------------

@router.patch(
    "/admin/products/{product_id}",
    response_model=ProductResponse,
)
def update_product(
    product_id: str,
    request: ProductUpdate,
    _: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(
        Product.product_id == product_id.strip().upper()
    ).first()

    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found.",
        )

    updates = request.model_dump(exclude_unset=True)

    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide at least one field to update.",
        )

    # These database columns cannot be NULL.
    for field in ("product_name", "price", "stock_quantity", "is_active"):
        if field in updates and updates[field] is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{field} cannot be null.",
            )

    for field, value in updates.items():
        setattr(product, field, value)

    try:
        db.commit()
        db.refresh(product)

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Product update violates a database constraint.",
        )

    return product


# ---------------------------------------------------------
# 4. CUSTOMER PRODUCT CATALOGUE
# ---------------------------------------------------------

@router.get(
    "/products",
    response_model=ProductListResponse,
)
def list_customer_products(
    category: str | None = None,
    search: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(Product).filter(
        Product.is_active.is_(True)
    )

    if category and category.strip():
        query = query.filter(
            Product.category.ilike(category.strip())
        )

    if search and search.strip():
        search_term = f"%{search.strip()}%"
        query = query.filter(
            Product.product_name.ilike(search_term)
            | Product.product_id.ilike(search_term)
            | Product.description.ilike(search_term)
        )

    total = query.count()

    products = (
        query
        .order_by(Product.product_name.asc(), Product.id.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "products": products,
    }


# ---------------------------------------------------------
# 5. CUSTOMER VIEW ONE PRODUCT
# ---------------------------------------------------------

@router.get(
    "/products/{product_id}",
    response_model=ProductResponse,
)
def get_customer_product(
    product_id: str,
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(
        Product.product_id == product_id.strip().upper(),
        Product.is_active.is_(True),
    ).first()

    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found or currently unavailable.",
        )

    return product

