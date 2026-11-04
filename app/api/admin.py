
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.core.dependencies import get_current_admin
from app.core.security import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    verify_password,
)
from app.db.models import (
    ActivityLog,
    ChatLog,
    Customer,
    Order,
)
from app.db.session import get_db
from app.schemas.auth import TokenResponse


router = APIRouter(prefix="/admin", tags=["Administrator"])


class AdminLoginRequest(BaseModel):
    identifier: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=128)


# ---------------------------------------------------------
# 1. ADMIN LOGIN
# ---------------------------------------------------------

@router.post("/login", response_model=TokenResponse)
def admin_login(request: AdminLoginRequest):
    identifier = request.identifier.strip().lower()

    allowed_identifiers = {
        settings.ADMIN_USERNAME.strip().lower(),
        settings.ADMIN_EMAIL.strip().lower(),
    }

    if identifier not in allowed_identifiers:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid administrator credentials.",
        )

    if not verify_password(
        request.password,
        settings.ADMIN_PASSWORD_HASH,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid administrator credentials.",
        )

    token = create_access_token(
        subject=settings.ADMIN_USERNAME,
        role="admin",
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# ---------------------------------------------------------
# 2. LIST ALL CUSTOMERS
# ---------------------------------------------------------

@router.get("/customers")
def list_customers(
    limit: int = 50,
    offset: int = 0,
    _: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    if not 1 <= limit <= 100 or offset < 0:
        raise HTTPException(
            status_code=400,
            detail="Use limit between 1 and 100 and a non-negative offset.",
        )

    customers = (
        db.query(Customer)
        .order_by(Customer.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    total = db.query(Customer).count()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "customers": [
            {
                "id": customer.id,
                "username": customer.username,
                "full_name": customer.full_name,
                "email": customer.email,
                "is_active": customer.is_active,
                "is_email_verified": customer.is_email_verified,
                "created_at": customer.created_at,
            }
            for customer in customers
        ],
    }


# ---------------------------------------------------------
# 3. LIST ALL ORDERS WITH PRODUCTS AND SHIPMENTS
# ---------------------------------------------------------

@router.get("/orders")
def list_all_orders(
    limit: int = 50,
    offset: int = 0,
    _: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    if not 1 <= limit <= 100 or offset < 0:
        raise HTTPException(
            status_code=400,
            detail="Use limit between 1 and 100 and a non-negative offset.",
        )

    query = (
        db.query(Order)
        .options(
            joinedload(Order.customer),
            joinedload(Order.items),
            joinedload(Order.shipment),
        )
        .order_by(Order.created_at.desc())
    )

    total = db.query(Order).count()
    orders = query.offset(offset).limit(limit).all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "orders": [
            {
                "id": order.id,
                "order_number": order.order_number,
                "order_status": order.order_status,
                "payment_status": order.payment_status,
                "total_amount": order.total_amount,
                "created_at": order.created_at,
                "updated_at": order.updated_at,
                "customer": {
                    "id": order.customer.id,
                    "username": order.customer.username,
                    "full_name": order.customer.full_name,
                    "email": order.customer.email,
                },
                "items": [
                    {
                        "id": item.id,
                        "product_id": item.product_id,
                        "product_name": item.product_name,
                        "quantity": item.quantity,
                        "unit_price": item.unit_price,
                    }
                    for item in order.items
                ],
                "shipment": (
                    {
                        "courier_name": order.shipment.courier_name,
                        "tracking_number": order.shipment.tracking_number,
                        "shipment_status": order.shipment.shipment_status,
                        "estimated_delivery": order.shipment.estimated_delivery,
                        "shipped_at": order.shipment.shipped_at,
                        "delivered_at": order.shipment.delivered_at,
                    }
                    if order.shipment
                    else None
                ),
            }
            for order in orders
        ],
    }


# ---------------------------------------------------------
# 4. LIST ALL CHAT CONVERSATIONS
# ---------------------------------------------------------

@router.get("/chats")
def list_all_chats(
    limit: int = 50,
    offset: int = 0,
    _: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    if not 1 <= limit <= 100 or offset < 0:
        raise HTTPException(
            status_code=400,
            detail="Use limit between 1 and 100 and a non-negative offset.",
        )

    query = (
        db.query(ChatLog)
        .options(joinedload(ChatLog.customer))
        .order_by(ChatLog.created_at.desc())
    )

    total = db.query(ChatLog).count()
    chats = query.offset(offset).limit(limit).all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "chats": [
            {
                "id": chat.id,
                "customer_id": chat.customer_id,
                "customer": (
                    {
                        "username": chat.customer.username,
                        "full_name": chat.customer.full_name,
                        "email": chat.customer.email,
                    }
                    if chat.customer
                    else None
                ),
                "session_id": chat.session_id,
                "question": chat.question,
                "answer": chat.answer,
                "source_details": chat.source_details,
                "feedback": chat.feedback,
                "created_at": chat.created_at,
            }
            for chat in chats
        ],
    }


# ---------------------------------------------------------
# 5. LIST CUSTOMER ACTIVITY
# ---------------------------------------------------------

@router.get("/activity")
def list_activity(
    limit: int = 50,
    offset: int = 0,
    _: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    if not 1 <= limit <= 100 or offset < 0:
        raise HTTPException(
            status_code=400,
            detail="Use limit between 1 and 100 and a non-negative offset.",
        )

    query = (
        db.query(ActivityLog)
        .order_by(ActivityLog.created_at.desc())
    )

    total = db.query(ActivityLog).count()
    logs = query.offset(offset).limit(limit).all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "activities": [
            {
                "id": log.id,
                "customer_id": log.customer_id,
                "action": log.action,
                "details": log.details,
                "created_at": log.created_at,
            }
            for log in logs
        ],
    }

