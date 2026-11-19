
import json
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.api.routes import customer_routes
from app.models import ActivityLog, ChatLog, Order


def make_customer():
    return SimpleNamespace(
        id=1,
        username="testuser",
        full_name="Test User",
        email="test@example.com",
        is_active=True,
        is_email_verified=True,
        created_at=datetime.now(timezone.utc),
    )


def make_query_mock():
    query = MagicMock()
    query.filter.return_value = query
    query.options.return_value = query
    query.order_by.return_value = query
    query.offset.return_value = query
    query.limit.return_value = query
    return query


def test_get_customer_profile():
    customer = make_customer()

    result = customer_routes.get_customer_profile(
        current_customer=customer
    )

    assert result["id"] == customer.id
    assert result["username"] == customer.username
    assert result["email"] == customer.email


def test_get_customer_orders():
    customer = make_customer()

    order = SimpleNamespace(
        id=101,
        order_number="ORD-TEST001",
        order_status="processing",
        payment_status="pending",
        total_amount=Decimal("1500.00"),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        items=[
            SimpleNamespace(
                id=1,
                product_id="MOB-1001",
                product_name="Samsung Mobile",
                quantity=1,
                unit_price=Decimal("1500.00"),
            )
        ],
        shipment=None,
    )

    query = make_query_mock()
    query.count.return_value = 1
    query.all.return_value = [order]

    db = MagicMock()
    db.query.return_value = query

    result = customer_routes.get_customer_orders(
        limit=20,
        offset=0,
        current_customer=customer,
        db=db,
    )

    assert result["total_returned"] == 1
    assert result["limit"] == 20
    assert result["offset"] == 0
    assert len(result["orders"]) == 1
    assert result["orders"][0]["order_number"] == "ORD-TEST001"


def test_get_customer_chats():
    customer = make_customer()

    chat = SimpleNamespace(
        id=1,
        session_id="SESSION-001",
        question="Where is my order?",
        answer="Your order is being processed.",
        source_details=json.dumps([{"source": "order_data"}]),
        feedback=None,
        created_at=datetime.now(timezone.utc),
    )

    query = make_query_mock()
    query.count.return_value = 1
    query.all.return_value = [chat]

    db = MagicMock()
    db.query.return_value = query

    result = customer_routes.get_customer_chats(
        limit=20,
        offset=0,
        current_customer=customer,
        db=db,
    )

    assert result["total_returned"] == 1
    assert len(result["chats"]) == 1
    assert result["chats"][0]["question"] == "Where is my order?"
    assert result["chats"][0]["sources"] == [{"source": "order_data"}]


def test_get_customer_activity():
    customer = make_customer()

    activity = SimpleNamespace(
        id=1,
        action="order_created",
        details="Customer created an order",
        created_at=datetime.now(timezone.utc),
    )

    query = make_query_mock()
    query.count.return_value = 1
    query.all.return_value = [activity]

    db = MagicMock()
    db.query.return_value = query

    result = customer_routes.get_customer_activity(
        limit=20,
        offset=0,
        current_customer=customer,
        db=db,
    )

    assert result["total_returned"] == 1
    assert len(result["activities"]) == 1
    assert result["activities"][0]["action"] == "order_created"


def test_get_customer_chats_invalid_source_details():
    customer = make_customer()

    chat = SimpleNamespace(
        id=2,
        session_id="SESSION-002",
        question="Where is my refund?",
        answer="Your refund is being processed.",
        source_details="{invalid json",
        feedback=None,
        created_at=datetime.now(timezone.utc),
    )

    query = make_query_mock()
    query.count.return_value = 1
    query.all.return_value = [chat]

    db = MagicMock()
    db.query.return_value = query

    result = customer_routes.get_customer_chats(
        limit=20,
        offset=0,
        current_customer=customer,
        db=db,
    )

    assert result["total_returned"] == 1
    assert len(result["chats"]) == 1
    assert result["chats"][0]["question"] == "Where is my refund?"
    assert result["chats"][0]["sources"] == []

