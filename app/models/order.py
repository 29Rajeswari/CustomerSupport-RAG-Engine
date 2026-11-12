from typing import TYPE_CHECKING
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, utc_now

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.shipment import Shipment


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_number: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True, index=True
    )
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    order_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="processing"
    )
    payment_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending"
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    customer: Mapped["Customer"] = relationship(
        back_populates="orders"
    )
    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
    )
    shipment: Mapped["Shipment | None"] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        uselist=False,
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[str] = mapped_column(
        String(100), nullable=False
    )
    product_name: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    quantity: Mapped[int] = mapped_column(
        Integer, nullable=False
    )
    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False
    )

    order: Mapped["Order"] = relationship(
        back_populates="items"
    )
