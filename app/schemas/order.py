from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class OrderItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: str = Field(min_length=1, max_length=100)
    quantity: int = Field(gt=0, le=1000)

    @field_validator("product_id")
    @classmethod
    def normalize_product_id(cls, value: str) -> str:
        value = value.strip().upper()
        if not value:
            raise ValueError("Product ID cannot be empty.")
        return value


class OrderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[OrderItemCreate] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def reject_duplicate_products(self):
        product_ids = [item.product_id for item in self.items]

        if len(product_ids) != len(set(product_ids)):
            raise ValueError(
                "Each product must appear only once in an order."
            )

        return self