
from typing import TYPE_CHECKING
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utc_now

if TYPE_CHECKING:
    from app.models.order import Order
    from app.models.customer import Customer
    from app.models.order import OrderItem


# ---------------------------------------------------------
# RETURN REQUEST MODEL
# ---------------------------------------------------------

class ReturnRequest(Base):
    __tablename__ = "return_requests"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    return_number: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
        index=True,
    )

    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    reason: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    comments: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    admin_note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    return_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="pending_review",
        server_default="pending_review",
    )

    inspection_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="pending",
        server_default="pending",
    )

    restocked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    order: Mapped["Order"] = relationship()

    customer: Mapped["Customer"] = relationship()

    items: Mapped[list["ReturnItem"]] = relationship(
        back_populates="return_request",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            "return_status IN ("
            "'pending_review', "
            "'approved', "
            "'rejected', "
            "'completed'"
            ")",
            name="ck_return_requests_status",
        ),
    )


# ---------------------------------------------------------
# RETURN ITEM MODEL
# ---------------------------------------------------------

class ReturnItem(Base):
    __tablename__ = "return_items"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    return_id: Mapped[int] = mapped_column(
        ForeignKey("return_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    order_item_id: Mapped[int] = mapped_column(
        ForeignKey("order_items.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    return_request: Mapped["ReturnRequest"] = relationship(
        back_populates="items",
    )

    order_item: Mapped["OrderItem"] = relationship()

    __table_args__ = (
        CheckConstraint(
            "quantity > 0",
            name="ck_return_items_quantity_positive",
        ),
    )


# ---------------------------------------------------------
# REFUND MODEL
# ---------------------------------------------------------

class Refund(Base):
    __tablename__ = "refunds"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    refund_number: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
        index=True,
    )

    return_id: Mapped[int] = mapped_column(
        ForeignKey("return_requests.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
        index=True,
    )

    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    refund_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    refund_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="pending",
        server_default="pending",
    )

    payment_reference: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )

    admin_note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    __table_args__ = (
        CheckConstraint(
            "refund_amount >= 0",
            name="ck_refunds_amount_nonnegative",
        ),
        CheckConstraint(
            "refund_status IN ('pending', 'processed', 'failed')",
            name="ck_refunds_status",
        ),
    )
