#app\schemas\return_request.py

from pydantic import BaseModel, Field


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

    items: list[ReturnItemCreate] = Field(
        ...,
        min_length=1,
    )
