from pydantic import BaseModel, Field, ConfigDict
from typing import List


class ReturnItemCreate(BaseModel):
    order_item_id: int = Field(..., gt=0)
    quantity: int = Field(..., gt=0)


class ReturnRequestCreate(BaseModel):
    reason: str = Field(
        ...,
        min_length=3,
        max_length=100,
    )

    comments: str | None = Field(
        default=None,
        max_length=1000,
    )

    items: List[ReturnItemCreate] = Field(
        ...,
        min_length=1,
    )