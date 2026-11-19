
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.api.routes import customer_routes
from app.models import Order, OrderItem, Product


@pytest.fixture
def customer():
    return SimpleNamespace(id=7)


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def order():
    return SimpleNamespace(
        id=101,
        order_number="ORD-ABC123",
        customer_id=7,
        order_status="processing",
        payment_status="pending",
        shipment=None,
    )


@pytest.fixture
def purchased_item():
    return SimpleNamespace(
        id=1,
        product_id="MOB-1001",
        product_name="Samsung Mobile",
        quantity=2,
    )


@pytest.fixture
def product():
    return SimpleNamespace(
        product_id="MOB-1001",
        product_name="Samsung Mobile",
        stock_quantity=8,
    )


@pytest.fixture
def setup_order_query(mock_db):
    query = mock_db.query.return_value
    query.filter.return_value = query
    query.with_for_update.return_value = query
    query.order_by.return_value = query
    return query


def test_cancel_order_success(
    mock_db, customer, order, purchased_item, product, setup_order_query
):
    """A valid cancellation restores purchased inventory."""

    setup_order_query.first.return_value = order
    setup_order_query.all.side_effect = [
        [purchased_item],
        [product],
    ]

    result = customer_routes.cancel_customer_order(
        order_id=101,
        current_customer=customer,
        db=mock_db,
    )

    assert result["message"] == "Order cancelled successfully."
    assert result["order_id"] == 101
    assert result["order_number"] == "ORD-ABC123"
    assert result["order_status"] == "cancelled"

    assert product.stock_quantity == 10
    assert result["restored_products"][0]["restored_quantity"] == 2
    assert result["restored_products"][0]["available_stock"] == 10

    assert order.order_status == "cancelled"
    mock_db.commit.assert_called_once()
    mock_db.rollback.assert_not_called()


def test_cancel_order_not_found(
    mock_db, customer, setup_order_query
):
    """A nonexistent order should return 404."""

    setup_order_query.first.return_value = None

    with pytest.raises(HTTPException) as exc:
        customer_routes.cancel_customer_order(
            order_id=999,
            current_customer=customer,
            db=mock_db,
        )

    assert exc.value.status_code == 404
    assert exc.value.detail == "Order not found."

    mock_db.rollback.assert_called_once()
    mock_db.commit.assert_not_called()


def test_cancel_already_cancelled_order(
    mock_db, customer, order, setup_order_query
):
    """An already cancelled order cannot be cancelled again."""

    order.order_status = "cancelled"
    setup_order_query.first.return_value = order

    with pytest.raises(HTTPException) as exc:
        customer_routes.cancel_customer_order(
            order_id=101,
            current_customer=customer,
            db=mock_db,
        )

    assert exc.value.status_code == 409
    assert exc.value.detail == "This order has already been cancelled."

    mock_db.commit.assert_not_called()
    mock_db.rollback.assert_called_once()


@pytest.mark.parametrize("order_status", ["delivered", "shipped", "processing_review"])
def test_cancel_non_processing_order(
    mock_db, customer, order, setup_order_query, order_status
):
    """Only processing orders can be cancelled."""

    order.order_status = order_status
    setup_order_query.first.return_value = order

    with pytest.raises(HTTPException) as exc:
        customer_routes.cancel_customer_order(
            order_id=101,
            current_customer=customer,
            db=mock_db,
        )

    assert exc.value.status_code == 409
    assert exc.value.detail == "Only processing orders can be cancelled."

    mock_db.commit.assert_not_called()
    mock_db.rollback.assert_called_once()


def test_cancel_paid_order(
    mock_db, customer, order, setup_order_query
):
    """Only pending-payment orders can be cancelled."""

    order.payment_status = "paid"
    setup_order_query.first.return_value = order

    with pytest.raises(HTTPException) as exc:
        customer_routes.cancel_customer_order(
            order_id=101,
            current_customer=customer,
            db=mock_db,
        )

    assert exc.value.status_code == 409
    assert exc.value.detail == "Only orders with pending payment can be cancelled."

    mock_db.commit.assert_not_called()


def test_cancel_shipment_already_started(
    mock_db, customer, order, setup_order_query
):
    """An order cannot be cancelled after shipment has started."""

    order.shipment = SimpleNamespace(
        shipment_status="shipped"
    )
    setup_order_query.first.return_value = order

    with pytest.raises(HTTPException) as exc:
        customer_routes.cancel_customer_order(
            order_id=101,
            current_customer=customer,
            db=mock_db,
        )

    assert exc.value.status_code == 409
    assert "shipment has started" in exc.value.detail

    mock_db.commit.assert_not_called()


def test_cancel_order_without_items(
    mock_db, customer, order, setup_order_query
):
    """An order without order items cannot be cancelled."""

    setup_order_query.first.return_value = order
    setup_order_query.all.return_value = []

    with pytest.raises(HTTPException) as exc:
        customer_routes.cancel_customer_order(
            order_id=101,
            current_customer=customer,
            db=mock_db,
        )

    assert exc.value.status_code == 409
    assert exc.value.detail == "No order items were found."

    mock_db.commit.assert_not_called()


def test_cancel_order_product_missing(
    mock_db, customer, order, purchased_item, setup_order_query
):
    """Cancellation fails if a purchased product no longer exists."""

    setup_order_query.first.return_value = order
    setup_order_query.all.side_effect = [
        [purchased_item],
        [],
    ]

    with pytest.raises(HTTPException) as exc:
        customer_routes.cancel_customer_order(
            order_id=101,
            current_customer=customer,
            db=mock_db,
        )

    assert exc.value.status_code == 409
    assert "product MOB-1001 was not found" in exc.value.detail

    mock_db.commit.assert_not_called()


def test_cancel_order_multiple_products(
    mock_db, customer, order, setup_order_query
):
    """Cancellation restores inventory for every purchased product."""

    mobile_item = SimpleNamespace(
        product_id="MOB-1001",
        product_name="Samsung Mobile",
        quantity=2,
    )

    laptop_item = SimpleNamespace(
        product_id="LAP-1001",
        product_name="Laptop",
        quantity=1,
    )

    mobile = SimpleNamespace(
        product_id="MOB-1001",
        product_name="Samsung Mobile",
        stock_quantity=8,
    )

    laptop = SimpleNamespace(
        product_id="LAP-1001",
        product_name="Laptop",
        stock_quantity=4,
    )

    setup_order_query.first.return_value = order
    setup_order_query.all.side_effect = [
        [mobile_item, laptop_item],
        [laptop, mobile],
    ]

    result = customer_routes.cancel_customer_order(
        order_id=101,
        current_customer=customer,
        db=mock_db,
    )

    assert mobile.stock_quantity == 10
    assert laptop.stock_quantity == 5
    assert len(result["restored_products"]) == 2

    mock_db.commit.assert_called_once()


def test_cancel_order_commit_failure(
    mock_db, customer, order, purchased_item, product, setup_order_query
):
    """A commit failure triggers rollback."""

    setup_order_query.first.return_value = order
    setup_order_query.all.side_effect = [
        [purchased_item],
        [product],
    ]

    mock_db.commit.side_effect = RuntimeError("Database commit failed")

    with pytest.raises(RuntimeError, match="Database commit failed"):
        customer_routes.cancel_customer_order(
            order_id=101,
            current_customer=customer,
            db=mock_db,
        )

    assert product.stock_quantity == 10
    assert order.order_status == "cancelled"

    mock_db.commit.assert_called_once()
    mock_db.rollback.assert_called_once()
