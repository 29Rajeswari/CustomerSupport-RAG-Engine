#tests/api/test_customer_returns.py

from app.models.return_request import Refund, ReturnItem, ReturnRequest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock


from decimal import Decimal
from types import SimpleNamespace


import pytest
from fastapi import HTTPException

from app.api.routes import customer_routes
from app.models.order import Order, OrderItem
from app.models.return_request import ReturnItem, ReturnRequest
from app.schemas.return_request import ReturnRequestCreate


def make_customer():
    return SimpleNamespace(id=1)


def make_order(status="delivered"):
    return SimpleNamespace(
        id=101,
        customer_id=1,
        order_number="ORD-TEST001",
        order_status=status,
    )


def make_order_item(
    item_id=10,
    quantity=3,
    product_id="MOB-1001",
):
    return SimpleNamespace(
        id=item_id,
        order_id=101,
        product_id=product_id,
        product_name="Samsung Mobile",
        quantity=quantity,
    )


def make_request(items=None, reason="Damaged product", comments="Box was damaged"):
    if items is None:
        items = [{"order_item_id": 10, "quantity": 1}]

    return ReturnRequestCreate(
        reason=reason,
        comments=comments,
        items=items,
    )


def make_query(first=None, all_items=None):
    query = MagicMock()
    query.filter.return_value = query
    query.with_for_update.return_value = query
    query.order_by.return_value = query
    query.join.return_value = query
    query.first.return_value = first
    query.all.return_value = all_items or []
    return query


def make_db(
    order=None,
    existing_request=None,
    order_items=None,
    previous_returns=None,
):
    order_query = make_query(first=order)
    existing_query = make_query(first=existing_request)
    items_query = make_query(all_items=order_items)
    previous_query = make_query(all_items=previous_returns)

    db = MagicMock()
    db.query.side_effect = [
        order_query,
        existing_query,
        items_query,
        previous_query,
    ]

    added_objects = []
    db.add.side_effect = added_objects.append

    def assign_generated_id():
        for obj in added_objects:
            if isinstance(obj, ReturnRequest) and obj.id is None:
                obj.id = 501

    db.flush.side_effect = assign_generated_id

    return db, added_objects


def test_create_return_request_success():
    customer = make_customer()
    order = make_order()
    order_item = make_order_item(quantity=3)

    db, added_objects = make_db(
        order=order,
        order_items=[order_item],
    )

    result = customer_routes.create_return_request(
        order_id=101,
        request=make_request(
            items=[{"order_item_id": 10, "quantity": 2}],
            reason="  Damaged product  ",
            comments="  Box was damaged  ",
        ),
        current_customer=customer,
        db=db,
    )

    assert result["message"] == "Return request submitted successfully."
    assert result["return_id"] == 501
    assert result["order_id"] == 101
    assert result["order_number"] == "ORD-TEST001"
    assert result["reason"] == "Damaged product"
    assert result["comments"] == "Box was damaged"
    assert result["return_status"] == "pending_review"

    assert result["items"] == [
        {
            "order_item_id": 10,
            "product_id": "MOB-1001",
            "product_name": "Samsung Mobile",
            "purchased_quantity": 3,
            "return_quantity": 2,
        }
    ]

    assert any(isinstance(obj, ReturnRequest) for obj in added_objects)
    assert any(isinstance(obj, ReturnItem) for obj in added_objects)
    db.commit.assert_called_once()
    db.refresh.assert_called_once()
    db.rollback.assert_not_called()


def test_create_return_request_order_not_found():
    db, _ = make_db(order=None)

    with pytest.raises(HTTPException) as exc:
        customer_routes.create_return_request(
            order_id=101,
            request=make_request(),
            current_customer=make_customer(),
            db=db,
        )

    assert exc.value.status_code == 404
    assert exc.value.detail == "Order not found."
    db.rollback.assert_called_once()
    db.commit.assert_not_called()


def test_create_return_request_order_not_delivered():
    db, _ = make_db(order=make_order(status="processing"))

    with pytest.raises(HTTPException) as exc:
        customer_routes.create_return_request(
            order_id=101,
            request=make_request(),
            current_customer=make_customer(),
            db=db,
        )

    assert exc.value.status_code == 400
    assert "only be submitted for delivered orders" in exc.value.detail
    db.rollback.assert_called_once()


def test_create_return_request_active_request_exists():
    existing = SimpleNamespace(
        id=501,
        return_status="pending_review",
    )

    db, _ = make_db(
        order=make_order(),
        existing_request=existing,
    )

    with pytest.raises(HTTPException) as exc:
        customer_routes.create_return_request(
            order_id=101,
            request=make_request(),
            current_customer=make_customer(),
            db=db,
        )

    assert exc.value.status_code == 409
    assert "active return request already exists" in exc.value.detail
    db.rollback.assert_called_once()


def test_create_return_request_duplicate_item_ids():
    db, _ = make_db(order=make_order())

    with pytest.raises(HTTPException) as exc:
        customer_routes.create_return_request(
            order_id=101,
            request=make_request(
                items=[
                    {"order_item_id": 10, "quantity": 1},
                    {"order_item_id": 10, "quantity": 1},
                ]
            ),
            current_customer=make_customer(),
            db=db,
        )

    assert exc.value.status_code == 422
    assert exc.value.detail == "Duplicate order item IDs are not allowed."
    db.rollback.assert_called_once()


def test_create_return_request_item_does_not_belong_to_order():
    db, _ = make_db(
        order=make_order(),
        order_items=[],
    )

    with pytest.raises(HTTPException) as exc:
        customer_routes.create_return_request(
            order_id=101,
            request=make_request(),
            current_customer=make_customer(),
            db=db,
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "One or more items do not belong to this order."
    db.rollback.assert_called_once()


def test_create_return_request_quantity_exceeds_purchased_quantity():
    db, _ = make_db(
        order=make_order(),
        order_items=[make_order_item(quantity=2)],
    )

    with pytest.raises(HTTPException) as exc:
        customer_routes.create_return_request(
            order_id=101,
            request=make_request(
                items=[{"order_item_id": 10, "quantity": 3}]
            ),
            current_customer=make_customer(),
            db=db,
        )

    assert exc.value.status_code == 409
    assert exc.value.detail["remaining_quantity"] == 2
    assert exc.value.detail["requested_quantity"] == 3
    db.rollback.assert_called_once()


def test_create_return_request_quantity_exceeds_remaining_after_previous_return():
    previous_return_item = SimpleNamespace(
        order_item_id=10,
        quantity=2,
    )
    previous_request = SimpleNamespace(
        return_status="approved",
    )

    db, _ = make_db(
        order=make_order(),
        order_items=[make_order_item(quantity=3)],
        previous_returns=[(previous_return_item, previous_request)],
    )

    with pytest.raises(HTTPException) as exc:
        customer_routes.create_return_request(
            order_id=101,
            request=make_request(
                items=[{"order_item_id": 10, "quantity": 2}]
            ),
            current_customer=make_customer(),
            db=db,
        )

    assert exc.value.status_code == 409
    assert exc.value.detail["purchased_quantity"] == 3
    assert exc.value.detail["previously_returned"] == 2
    assert exc.value.detail["remaining_quantity"] == 1
    assert exc.value.detail["requested_quantity"] == 2
    db.rollback.assert_called_once()



def test_create_return_request_rejected_previous_return_does_not_reduce_quantity():
    # The database query excludes rejected return requests.
    # Therefore, the mocked query must return an empty result.
    db, _ = make_db(
        order=make_order(),
        order_items=[make_order_item(quantity=3)],
        previous_returns=[],
    )

    result = customer_routes.create_return_request(
        order_id=101,
        request=make_request(
            items=[{"order_item_id": 10, "quantity": 3}]
        ),
        current_customer=make_customer(),
        db=db,
    )

    assert result["return_status"] == "pending_review"
    assert result["items"][0]["purchased_quantity"] == 3
    assert result["items"][0]["return_quantity"] == 3
    db.commit.assert_called_once()
    db.rollback.assert_not_called()


def test_create_return_request_commit_failure_rolls_back():
    db, _ = make_db(
        order=make_order(),
        order_items=[make_order_item(quantity=3)],
    )
    db.commit.side_effect = RuntimeError("Database commit failed")

    with pytest.raises(RuntimeError, match="Database commit failed"):
        customer_routes.create_return_request(
            order_id=101,
            request=make_request(),
            current_customer=make_customer(),
            db=db,
        )

    db.commit.assert_called_once()
    db.rollback.assert_called_once()


def test_get_customer_return_request_success():
    return_request = SimpleNamespace(
        id=501,
        return_number="RET-TEST123",
        order_id=101,
        customer_id=1,
        reason="Damaged product",
        comments="Box was damaged",
        return_status="pending_review",
        created_at="2026-11-17T10:00:00",
        updated_at="2026-11-17T10:00:00",
    )

    db = MagicMock()
    query = db.query.return_value
    query.filter.return_value = query
    query.first.return_value = return_request

    result = customer_routes.get_customer_return_request(
        return_number="RET-TEST123",
        current_customer=make_customer(),
        db=db,
    )

    assert result["return_id"] == 501
    assert result["return_number"] == "RET-TEST123"
    assert result["order_id"] == 101
    assert result["reason"] == "Damaged product"
    assert result["comments"] == "Box was damaged"
    assert result["return_status"] == "pending_review"
    assert result["created_at"] == return_request.created_at
    assert result["updated_at"] == return_request.updated_at


def test_get_customer_return_request_not_found():
    db = MagicMock()
    query = db.query.return_value
    query.filter.return_value = query
    query.first.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        customer_routes.get_customer_return_request(
            return_number="RET-UNKNOWN",
            current_customer=make_customer(),
            db=db,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Return request not found."


def test_get_customer_refunds_success():
    refund_1 = SimpleNamespace(
        id=1,
        refund_number="REF-TEST001",
        return_id=501,
        order_id=101,
        refund_amount=Decimal("1500.00"),
        refund_status="processed",
        payment_reference="PAY-001",
        admin_note="Refund completed",
        created_at="2026-11-16T10:00:00",
        updated_at="2026-11-16T11:00:00",
    )

    refund_2 = SimpleNamespace(
        id=2,
        refund_number="REF-TEST002",
        return_id=502,
        order_id=102,
        refund_amount=Decimal("500.50"),
        refund_status="pending",
        payment_reference=None,
        admin_note=None,
        created_at="2026-11-17T10:00:00",
        updated_at="2026-11-17T10:00:00",
    )

    db = MagicMock()
    query = db.query.return_value
    query.filter.return_value = query
    query.order_by.return_value = query
    query.all.return_value = [refund_2, refund_1]

    result = customer_routes.get_customer_refunds(
        current_customer=make_customer(),
        db=db,
    )

    assert result["total"] == 2
    assert len(result["refunds"]) == 2

    assert result["refunds"][0]["refund_id"] == 2
    assert result["refunds"][0]["refund_number"] == "REF-TEST002"
    assert result["refunds"][0]["refund_amount"] == "500.50"
    assert result["refunds"][0]["refund_status"] == "pending"
    assert result["refunds"][0]["payment_reference"] is None
    assert result["refunds"][0]["admin_note"] is None

    assert result["refunds"][1]["refund_id"] == 1
    assert result["refunds"][1]["refund_number"] == "REF-TEST001"
    assert result["refunds"][1]["refund_amount"] == "1500.00"
    assert result["refunds"][1]["refund_status"] == "processed"


def test_get_customer_refunds_empty():
    db = MagicMock()
    query = db.query.return_value
    query.filter.return_value = query
    query.order_by.return_value = query
    query.all.return_value = []

    result = customer_routes.get_customer_refunds(
        current_customer=make_customer(),
        db=db,
    )

    assert result == {
        "total": 0,
        "refunds": [],
    }
