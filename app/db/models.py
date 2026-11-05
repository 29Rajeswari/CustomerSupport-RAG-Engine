
from datetime import datetime, timezone
from decimal import Decimal

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------
# 1. DOCUMENTS
# ---------------------------------------------------------

class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(
        String(100), nullable=False, default="general"
    )
    product_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending", index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    versions: Mapped[list["DocumentVersion"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentVersion.version_number",
    )


# ---------------------------------------------------------
# 2. DOCUMENT VERSIONS
# ---------------------------------------------------------

class DocumentVersion(Base):
    __tablename__ = "document_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    file_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    product_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="processing", index=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True
    )
    effective_from: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    effective_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    document: Mapped["Document"] = relationship(back_populates="versions")
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="version",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "version_number",
            name="uq_document_version_number",
        ),
    )


# ---------------------------------------------------------
# 3. DOCUMENT CHUNKS
# ---------------------------------------------------------

class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_id: Mapped[int] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    product_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    category: Mapped[str] = mapped_column(
        String(100), nullable=False, default="general"
    )
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(768), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    version: Mapped["DocumentVersion"] = relationship(
        back_populates="chunks"
    )

    __table_args__ = (
        UniqueConstraint(
            "version_id",
            "chunk_index",
            name="uq_version_chunk_index",
        ),
    )


# ---------------------------------------------------------
# 4. FAQS
# ---------------------------------------------------------

class FAQ(Base):
    __tablename__ = "faqs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(
        String(100), nullable=False, default="general"
    )
    product_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_approved: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True
    )
    source_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("document_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    needs_review: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
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


# ---------------------------------------------------------
# 5. CHAT LOGS
# ---------------------------------------------------------

class ChatLog(Base):
    __tablename__ = "chat_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Nullable to preserve historical chats without ownership.
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    session_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    source_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    feedback: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    customer: Mapped["Customer | None"] = relationship(
        back_populates="chat_logs"
    )


# ---------------------------------------------------------
# 6. CUSTOMERS
# ---------------------------------------------------------

class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    username: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True, index=True
    )

    full_name: Mapped[str] = mapped_column(
        String(150), nullable=False
    )
    email: Mapped[str] = mapped_column(
        String(254), nullable=False, unique=True, index=True
    )
    password_hash: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    is_email_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    orders: Mapped[list["Order"]] = relationship(
        back_populates="customer"
    )
    chat_logs: Mapped[list["ChatLog"]] = relationship(
        back_populates="customer"
    )


# ---------------------------------------------------------
# 7. ORDERS
# ---------------------------------------------------------

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


# ---------------------------------------------------------
# 8. ORDER ITEMS
# ---------------------------------------------------------

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


# ---------------------------------------------------------
# 9. SHIPMENTS
# ---------------------------------------------------------

class Shipment(Base):
    __tablename__ = "shipments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    courier_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    tracking_number: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    shipment_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="not_shipped"
    )
    estimated_delivery: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    shipped_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    order: Mapped["Order"] = relationship(
        back_populates="shipment"
    )


# ---------------------------------------------------------
# 10. LEGACY EMAIL VERIFICATIONS
# Retained for compatibility with the previous registration flow.
# ---------------------------------------------------------

class EmailVerification(Base):
    __tablename__ = "email_verifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    otp_hash: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    is_used: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default="now()",
    )

    customer: Mapped["Customer"] = relationship()


# ---------------------------------------------------------
# 11. PENDING REGISTRATIONS
# OTP verification before creating a Customer account.
# ---------------------------------------------------------

class PendingRegistration(Base):
    __tablename__ = "pending_registrations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    email: Mapped[str] = mapped_column(
        String(254), nullable=False, unique=True, index=True
    )

    otp_hash: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    is_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default="now()",
    )


# ---------------------------------------------------------
# 12. ACTIVITY LOGS
# ---------------------------------------------------------

class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )
    details: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default="now()",
        index=True,
    )


# ---------------------------------------------------------
# PASSWORD RESET OTP
# Separate OTP storage for customer password recovery.
# ---------------------------------------------------------

class PasswordResetOTP(Base):
    __tablename__ = "password_reset_otps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    otp_hash: Mapped[str] = mapped_column(
        String(255), nullable=False
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    is_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    last_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default="now()",
    )

    customer: Mapped["Customer"] = relationship()


# ---------------------------------------------------------
# 13. PRODUCTS
# ---------------------------------------------------------

class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    product_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        index=True,
    )

    product_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    category: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )

    price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    stock_quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
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
            "price >= 0",
            name="ck_products_price_nonnegative",
        ),
        CheckConstraint(
            "stock_quantity >= 0",
            name="ck_products_stock_nonnegative",
        ),
    )

# ---------------------------------------------------------
# 14. CUSTOMER RETURN REQUESTS
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
# 14. CUSTOMER RETURN REQUESTS
# ---------------------------------------------------------
