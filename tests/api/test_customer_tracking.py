
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.api.routes.customer_routes import track_customer_order


@pytest.fixture
def customer():
    return SimpleNamespace(id=1)


@pytest.fixture
def mock_db():
    return MagicMock()


def test_track_order_success(customer, mock_db):
    """Verify tracking details are returned for an order with a shipment."""

    created_at = datetime(2026, 10, 20, 10, 30)

    order = SimpleNamespace(
        id=10,
        customer_id=1,
        order_number="ORD-12345",
        order_status="shipped",
        shipment=SimpleNamespace(
            id=100,
            courier_name="BlueDart",
            tracking_number="BD123456",
            shipment_status="in_transit",
            estimated_delivery=created_at,
            shipped_at=created_at,
            delivered_at=None,
        ),
    )

    event = SimpleNamespace(
        status="in_transit",
        location="Hyderabad",
        description="Package reached the sorting facility",
        created_at=created_at,
    )

    order_query = MagicMock()
    order_query.options.return_value.filter.return_value.first.return_value = (
        order
    )

    event_query = MagicMock()
    (
        event_query.filter.return_value
        .order_by.return_value
        .all.return_value
    ) = [event]

    mock_db.query.side_effect = [order_query, event_query]

    result = track_customer_order(
        order_id=10,
        current_customer=customer,
        db=mock_db,
    )

    assert result["order_id"] == 10
    assert result["order_number"] == "ORD-12345"
    assert result["order_status"] == "shipped"

    assert result["shipment"]["courier_name"] == "BlueDart"
    assert result["shipment"]["tracking_number"] == "BD123456"
    assert result["shipment"]["shipment_status"] == "in_transit"

    assert len(result["shipment"]["events"]) == 1
    assert result["shipment"]["events"][0]["location"] == "Hyderabad"


def test_track_order_not_found(customer, mock_db):
    """Verify a 404 response when the customer's order does not exist."""

    order_query = MagicMock()
    order_query.options.return_value.filter.return_value.first.return_value = (
        None
    )

    mock_db.query.return_value = order_query

    with pytest.raises(HTTPException) as exc_info:
        track_customer_order(
            order_id=999,
            current_customer=customer,
            db=mock_db,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Order not found."

    # Shipment events should not be queried.
    assert mock_db.query.call_count == 1


def test_track_order_shipment_not_created(customer, mock_db):
    """Verify a 404 response when the order has no shipment."""

    order = SimpleNamespace(
        id=10,
        customer_id=1,
        order_number="ORD-12345",
        order_status="processing",
        shipment=None,
    )

    order_query = MagicMock()
    order_query.options.return_value.filter.return_value.first.return_value = (
        order
    )

    mock_db.query.return_value = order_query

    with pytest.raises(HTTPException) as exc_info:
        track_customer_order(
            order_id=10,
            current_customer=customer,
            db=mock_db,
        )

    assert exc_info.value.status_code == 404
    assert (
        exc_info.value.detail
        == "Shipment has not been created for this order yet."
    )

    # ShipmentEvent must not be queried when shipment is missing.
    assert mock_db.query.call_count == 1
