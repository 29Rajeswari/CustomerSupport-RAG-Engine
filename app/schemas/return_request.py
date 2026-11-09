from pydantic import BaseModel, Field


class ReturnRequestCreate(BaseModel):
    reason: str = Field(
        ...,
        min_length=3,
        max_length=100,
        description="Reason for requesting a return",
    )

    comments: str | None = Field(
        default=None,
        max_length=1000,
        description="Additional details about the return",
    )