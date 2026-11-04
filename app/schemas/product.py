
from datetime import datetime
from decimal import Decimal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


# ---------------------------------------------------------
# COMMON PRODUCT VALIDATION
# ---------------------------------------------------------

def normalize_product_id(value: str) -> str:
    value = value.strip().upper()

    if not value:
        raise ValueError("Product ID cannot be empty.")

    return value


def normalize_product_name(value: str) -> str:
    value = value.strip()

    if not value:
        raise ValueError("Product name cannot be empty.")

    return value


# ---------------------------------------------------------
# 1. CREATE PRODUCT
# ---------------------------------------------------------

class ProductCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: str = Field(min_length=1, max_length=100)
    product_name: str = Field(min_length=1, max_length=255)

    description: str | None = None
    category: str | None = Field(default=None, max_length=100)

    price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    stock_quantity: int = Field(ge=0)

    @field_validator("product_id")
    @classmethod
    def validate_product_id(cls, value: str) -> str:
        return normalize_product_id(value)

    @field_validator("product_name")
    @classmethod
    def validate_product_name(cls, value: str) -> str:
        return normalize_product_name(value)

    @field_validator("description", "category")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is not None:
            value = value.strip()
            return value or None

        return value


# ---------------------------------------------------------
# 2. UPDATE PRODUCT
# ---------------------------------------------------------

class ProductUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
    )

    description: str | None = None

    category: str | None = Field(
        default=None,
        max_length=100,
    )

    price: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=12,
        decimal_places=2,
    )

    stock_quantity: int | None = Field(
        default=None,
        ge=0,
    )

    is_active: bool | None = None

    @field_validator("product_name")
    @classmethod
    def validate_product_name(cls, value: str | None) -> str | None:
        if value is not None:
            return normalize_product_name(value)

        return value

    @field_validator("description", "category")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is not None:
            value = value.strip()
            return value or None

        return value


# ---------------------------------------------------------
# 3. PRODUCT RESPONSE
# ---------------------------------------------------------

class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: str
    product_name: str
    description: str | None
    category: str | None
    price: Decimal
    stock_quantity: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------
# 4. PRODUCT LIST RESPONSE
# ---------------------------------------------------------

class ProductListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    products: list[ProductResponse]

