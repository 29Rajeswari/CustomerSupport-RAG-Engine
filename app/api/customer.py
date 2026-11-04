import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload

from app.core.dependencies import get_current_customer
from app.db.models import ActivityLog, ChatLog, Customer, Order
from app.db.session import get_db


router = APIRouter(prefix="/customer", tags=["Customer"])


# ---------------------------------------------------------
# 1. CUSTOMER PROFILE
# ---------------------------------------------------------

@router.get("/profile")
def get_customer_profile(
    current_customer: Customer = Depends(get_current_customer),
):
    return {
        "id": current_customer.id,
        "username": current_customer.username,
        "full_name": current_customer.full_name,
        "email": current_customer.email,
        "is_active": current_customer.is_active,
        "is_email_verified": current_customer.is_email_verified,
        "created_at": current_customer.created_at,
    }


# ---------------------------------------------------------
# 2. CUSTOMER ORDERS
# ---------------------------------------------------------

@router.get("/orders")
def get_customer_orders(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    orders = (
        db.query(Order)
        .options(
            joinedload(Order.items),
            joinedload(Order.shipment),
        )
        .filter(Order.customer_id == current_customer.id)
        .order_by(Order.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    results = []

    for order in orders:
        shipment = order.shipment

        results.append({
            "id": order.id,
            "order_number": order.order_number,
            "order_status": order.order_status,
            "payment_status": order.payment_status,
            "total_amount": order.total_amount,
            "created_at": order.created_at,
            "updated_at": order.updated_at,
            "products": [
                {
                    "product_id": item.product_id,
                    "product_name": item.product_name,
                    "quantity": item.quantity,
                    "unit_price": item.unit_price,
                    "subtotal": item.quantity * item.unit_price,
                }
                for item in order.items
            ],
            "shipment": (
                {
                    "courier_name": shipment.courier_name,
                    "tracking_number": shipment.tracking_number,
                    "shipment_status": shipment.shipment_status,
                    "estimated_delivery": shipment.estimated_delivery,
                    "shipped_at": shipment.shipped_at,
                    "delivered_at": shipment.delivered_at,
                }
                if shipment
                else None
            ),
        })

    return {
        "total_returned": len(results),
        "limit": limit,
        "offset": offset,
        "orders": results,
    }


# ---------------------------------------------------------
# 3. CUSTOMER CHAT HISTORY
# ---------------------------------------------------------

@router.get("/chats")
def get_customer_chats(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    chats = (
        db.query(ChatLog)
        .filter(ChatLog.customer_id == current_customer.id)
        .order_by(ChatLog.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    results = []

    for chat in chats:
        sources = []

        if chat.source_details:
            try:
                sources = json.loads(chat.source_details)
            except (json.JSONDecodeError, TypeError):
                sources = []

        results.append({
            "id": chat.id,
            "session_id": chat.session_id,
            "question": chat.question,
            "answer": chat.answer,
            "sources": sources,
            "feedback": chat.feedback,
            "created_at": chat.created_at,
        })

    return {
        "total_returned": len(results),
        "limit": limit,
        "offset": offset,
        "chats": results,
    }


# ---------------------------------------------------------
# 4. CUSTOMER ACTIVITY HISTORY
# ---------------------------------------------------------

@router.get("/activity")
def get_customer_activity(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    activities = (
        db.query(ActivityLog)
        .filter(ActivityLog.customer_id == current_customer.id)
        .order_by(ActivityLog.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "total_returned": len(activities),
        "limit": limit,
        "offset": offset,
        "activities": [
            {
                "id": activity.id,
                "action": activity.action,
                "details": activity.details,
                "created_at": activity.created_at,
            }
            for activity in activities
        ],
    }
