import csv
import io

from fastapi import File, UploadFile
from pydantic import ValidationError

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_admin
from app.models import Product
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



# ---------------------------------------------------------
# 6. BULK PRODUCT UPLOAD FROM CSV (ADMIN ONLY)
# ---------------------------------------------------------

@router.post(
    "/admin/products/upload-csv",
    status_code=status.HTTP_200_OK,
)
async def upload_products_csv(
    file: UploadFile = File(...),
    _: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    # 1. Validate file extension.
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please upload a CSV file.",
        )

    # 2. Read file and enforce a 5 MB limit.
    content = await file.read()

    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="CSV file must not exceed 5 MB.",
        )

    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded CSV file is empty.",
        )

    # 3. Decode CSV content.
    try:
        csv_text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV must use UTF-8 encoding.",
        )

    # Create a CSV stream.
    csv_stream = io.StringIO(csv_text, newline="")
    
    # Skip empty lines before the CSV header.
    while True:
        line_position = csv_stream.tell()
        line = csv_stream.readline()
    
        if line == "":
            break
    
        if line.strip():
            csv_stream.seek(line_position)
            break
    
    # Read CSV data.
    reader = csv.DictReader(csv_stream)
    
    if not reader.fieldnames:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV header row is missing.",
        )

    # Normalize column names.
    reader.fieldnames = [
        name.strip().lower() if name else ""
        for name in reader.fieldnames
    ]

    required_columns = {
        "product_id",
        "product_name",
        "price",
        "stock_quantity",
    }

    optional_columns = {
        "description",
        "category",
    }

    available_columns = set(reader.fieldnames)

    missing_columns = required_columns - available_columns
    unexpected_columns = (
        available_columns - required_columns - optional_columns
    )

    if missing_columns:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Required CSV columns are missing.",
                "missing_columns": sorted(missing_columns),
            },
        )

    if unexpected_columns:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Unexpected CSV columns found.",
                "unexpected_columns": sorted(unexpected_columns),
            },
        )

    # Reject duplicate column names.
    if len(reader.fieldnames) != len(set(reader.fieldnames)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV contains duplicate column names.",
        )

    # 4. Validate rows before making database changes.
    validated_products = []
    seen_ids = set()
    skipped_csv_duplicates = 0
    errors = []

    for row_number, row in enumerate(reader, start=2):
        # Ignore completely blank rows.
        if not row or not any(
            value and value.strip() for value in row.values()
            if isinstance(value, str)
        ):
            continue

        try:
            product_data = {
                key: (value.strip() if isinstance(value, str) else value)
                for key, value in row.items()
                if key is not None
            }

            product = ProductCreate.model_validate(product_data)

            if product.product_id in seen_ids:
                skipped_csv_duplicates += 1
                continue

            seen_ids.add(product.product_id)
            validated_products.append(product)

        except (ValidationError, ValueError, TypeError) as exc:
            errors.append({
                "row": row_number,
                "errors": (
                    exc.errors()
                    if isinstance(exc, ValidationError)
                    else str(exc)
                ),
            })

    if errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": (
                    "CSV validation failed. No products were inserted."
                ),
                "invalid_rows": errors,
            },
        )

    if not validated_products:
        return {
            "message": "No new products were available to insert.",
            "inserted_count": 0,
            "skipped_existing_count": 0,
            "skipped_csv_duplicate_count": skipped_csv_duplicates,
            "products": [],
        }

    # 5. Find product IDs that already exist in PostgreSQL.
    uploaded_ids = [
        product.product_id for product in validated_products
    ]

    existing_ids = set(
        db.query(Product.product_id)
        .filter(Product.product_id.in_(uploaded_ids))
        .all()
    )

    # SQLAlchemy query returns one-element tuples.
    existing_ids = {row[0] for row in existing_ids}

    new_products = []
    skipped_existing_count = 0

    for product in validated_products:
        if product.product_id in existing_ids:
            skipped_existing_count += 1
            continue

        new_products.append(
            Product(
                product_id=product.product_id,
                product_name=product.product_name,
                description=product.description,
                category=product.category,
                price=product.price,
                stock_quantity=product.stock_quantity,
                is_active=True,
            )
        )

    # 6. Insert all new products in one transaction.
    try:
        db.add_all(new_products)
        db.commit()

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "A product ID was inserted concurrently. "
                "No products from this upload were saved. "
                "Please upload the CSV again."
            ),
        )

    return {
        "message": "CSV processing completed successfully.",
        "inserted_count": len(new_products),
        "skipped_existing_count": skipped_existing_count,
        "skipped_csv_duplicate_count": skipped_csv_duplicates,
        "products": [
            {
                "product_id": product.product_id,
                "product_name": product.product_name,
                "price": product.price,
                "stock_quantity": product.stock_quantity,
            }
            for product in new_products
        ],
    }

