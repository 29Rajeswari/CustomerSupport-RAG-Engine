
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.api.routes import customer_routes
from app.models import Order, OrderItem, Product
from app.schemas.order import OrderCreate


@pytest.fixture
def customer():
    return SimpleNamespace(id=7)


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def product():
    return SimpleNamespace(
        id=1,
        product_id="MOB-1001",
        product_name="Samsung Mobile",
        price=Decimal("15000.00"),
        stock_quantity=10,
        is_active=True,
    )


@pytest.fixture
def setup_order_creation(mock_db, monkeypatch):
    """Prepare mocked database queries and order creation behavior."""

    query = mock_db.query.return_value
    query.filter.return_value = query
    query.order_by.return_value = query
    query.with_for_update.return_value = query

    def add_side_effect(obj):
        if isinstance(obj, Order):
            obj.id = 101
            obj.order_status = "processing"
            obj.payment_status = "pending"

    mock_db.add.side_effect = add_side_effect

    def flush_side_effect():
        # Simulate the database-generated order ID.
        for call in mock_db.add.call_args_list:
            obj = call.args[0]
            if isinstance(obj, Order):
                obj.id = 101

    mock_db.flush.side_effect = flush_side_effect

    monkeypatch.setattr(
        customer_routes,
        "uuid4",
        lambda: SimpleNamespace(hex="ABCDEF1234567890"),
    )

    return query


def test_create_order_success(
    mock_db, customer, product, setup_order_creation
):
    """A valid order should be created and inventory reduced."""

    setup_order_creation.all.return_value = [product]

    order_data = OrderCreate(
        items=[
            {
                "product_id": "MOB-1001",
                "quantity": 2,
            }
        ]
    )

    result = customer_routes.create_customer_order(
        order_data=order_data,
        current_customer=customer,
        db=mock_db,
    )

    assert result["message"] == "Order placed successfully."
    assert result["order_id"] == 101
    assert result["order_number"] == "ORD-ABCDEF123456"
    assert result["order_status"] == "processing"
    assert result["payment_status"] == "pending"

    assert result["total_amount"] == Decimal("30000.00")
    assert product.stock_quantity == 8

    assert result["products"][0]["product_id"] == "MOB-1001"
    assert result["products"][0]["quantity"] == 2
    assert result["products"][0]["unit_price"] == Decimal("15000.00")
    assert result["products"][0]["subtotal"] == Decimal("30000.00")
    assert result["products"][0]["remaining_stock"] == 8

    mock_db.commit.assert_called_once()
    mock_db.rollback.assert_not_called()

    added_items = [
        call.args[0]
        for call in mock_db.add.call_args_list
        if isinstance(call.args[0], OrderItem)
    ]

    assert len(added_items) == 1
    assert added_items[0].product_id == "MOB-1001"
    assert added_items[0].quantity == 2
    assert added_items[0].unit_price == Decimal("15000.00")


def test_create_order_product_not_found(
    mock_db, customer, setup_order_creation
):
    """A missing or inactive product should return 404."""

    setup_order_creation.all.return_value = []

    order_data = OrderCreate(
        items=[
            {
                "product_id": "INVALID-001",
                "quantity": 1,
            }
        ]
    )

    with pytest.raises(HTTPException) as exc:
        customer_routes.create_customer_order(
            order_data=order_data,
            current_customer=customer,
            db=mock_db,
        )

    assert exc.value.status_code == 404
    assert "not found or is inactive" in exc.value.detail

    mock_db.rollback.assert_called_once()
    mock_db.commit.assert_not_called()


def test_create_order_insufficient_stock(
    mock_db, customer, product, setup_order_creation
):
    """An order exceeding available stock should return 409."""

    product.stock_quantity = 2
    setup_order_creation.all.return_value = [product]

    order_data = OrderCreate(
        items=[
            {
                "product_id": "MOB-1001",
                "quantity": 5,
            }
        ]
    )

    with pytest.raises(HTTPException) as exc:
        customer_routes.create_customer_order(
            order_data=order_data,
            current_customer=customer,
            db=mock_db,
        )

    assert exc.value.status_code == 409
    assert exc.value.detail["message"] == "Insufficient product stock."
    assert exc.value.detail["available_stock"] == 2
    assert exc.value.detail["requested_quantity"] == 5

    # Inventory must remain unchanged.
    assert product.stock_quantity == 2

    mock_db.rollback.assert_called_once()
    mock_db.commit.assert_not_called()


def test_create_order_multiple_products(
    mock_db, customer, setup_order_creation
):
    """Multiple products should have correct totals and stock updates."""

    mobile = SimpleNamespace(
        product_id="MOB-1001",
        product_name="Samsung Mobile",
        price=Decimal("15000.00"),
        stock_quantity=10,
        is_active=True,
    )

    laptop = SimpleNamespace(
        product_id="LAP-1001",
        product_name="Laptop",
        price=Decimal("50000.00"),
        stock_quantity=5,
        is_active=True,
    )

    setup_order_creation.all.return_value = [laptop, mobile]

    order_data = OrderCreate(
        items=[
            {"product_id": "MOB-1001", "quantity": 2},
            {"product_id": "LAP-1001", "quantity": 1},
        ]
    )

    result = customer_routes.create_customer_order(
        order_data=order_data,
        current_customer=customer,
        db=mock_db,
    )

    assert result["total_amount"] == Decimal("80000.00")

    assert mobile.stock_quantity == 8
    assert laptop.stock_quantity == 4

    assert len(result["products"]) == 2

    assert result["products"][0]["subtotal"] == Decimal("30000.00")
    assert result["products"][1]["subtotal"] == Decimal("50000.00")

    mock_db.commit.assert_called_once()


def test_create_order_uses_database_price(
    mock_db, customer, product, setup_order_creation
):
    """The order must use the database price, not a customer-supplied price."""

    setup_order_creation.all.return_value = [product]

    order_data = OrderCreate(
        items=[
            {
                "product_id": "MOB-1001",
                "quantity": 1,
            }
        ]
    )

    result = customer_routes.create_customer_order(
        order_data=order_data,
        current_customer=customer,
        db=mock_db,
    )

    assert result["total_amount"] == Decimal("15000.00")
    assert result["products"][0]["unit_price"] == Decimal("15000.00")


def test_create_order_database_failure_rolls_back(
    mock_db, customer, product, setup_order_creation
):
    """A commit failure should trigger database rollback."""

    setup_order_creation.all.return_value = [product]
    mock_db.commit.side_effect = RuntimeError("Database commit failed")

    order_data = OrderCreate(
        items=[
            {
                "product_id": "MOB-1001",
                "quantity": 2,
            }
        ]
    )

    with pytest.raises(RuntimeError, match="Database commit failed"):
        customer_routes.create_customer_order(
            order_data=order_data,
            current_customer=customer,
            db=mock_db,
        )

    assert product.stock_quantity == 8
    mock_db.commit.assert_called_once()
    mock_db.rollback.assert_called_once()
