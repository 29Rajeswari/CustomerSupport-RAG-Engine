
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


ShipmentStatus = Literal[
    "not_shipped",
    "shipped",
    "in_transit",
    "out_for_delivery",
    "delivered",
    "returned",
]


class ShipmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    courier_name: str = Field(min_length=2, max_length=100)
    tracking_number: str = Field(min_length=3, max_length=100)
    estimated_delivery: datetime | None = None


class ShipmentStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shipment_status: ShipmentStatus

