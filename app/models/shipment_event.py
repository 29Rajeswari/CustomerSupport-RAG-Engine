from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ShipmentEvent(Base):
    __tablename__ = "shipment_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    shipment_id: Mapped[int] = mapped_column(
        ForeignKey("shipments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(String(30), nullable=False)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    location: Mapped[str | None] = mapped_column(String(150), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
