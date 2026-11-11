from uuid import uuid4
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload


from app.config import settings
from app.core.dependencies import get_current_admin
from app.core.security import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    verify_password,
)
from app.models import (
    ActivityLog,
    ChatLog,
    Customer,
    Order,
    OrderItem,
    Product,
    Shipment,
    ReturnRequest,
    Refund,
)
from app.db.session import get_db
from app.schemas.auth import TokenResponse
from app.schemas.shipment import (
    ShipmentCreate,
    ShipmentStatusUpdate,
)

router = APIRouter(prefix="/admin", tags=["Administrator"])


class AdminLoginRequest(BaseModel):
    identifier: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=128)

class AdminReturnRejectRequest(BaseModel):
    reason: str = Field(
        ...,
        min_length=3,
        max_length=1000,
        description="Reason for rejecting the return request",
    )

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


# ---------------------------------------------------------
# 6. CREATE SHIPMENT FOR AN ORDER
# ---------------------------------------------------------

@router.post("/orders/{order_id}/shipment", status_code=201)
def create_shipment(
    order_id: int,
    shipment_data: ShipmentCreate,
    _: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    try:
        order = (
            db.query(Order)
            .filter(Order.id == order_id)
            .with_for_update()
            .first()
        )

        if order is None:
            raise HTTPException(
                status_code=404,
                detail="Order not found.",
            )

        if order.order_status == "cancelled":
            raise HTTPException(
                status_code=409,
                detail="Cannot create shipment for a cancelled order.",
            )

        if order.order_status != "processing":
            raise HTTPException(
                status_code=409,
                detail="Shipment can only be created for processing orders.",
            )

        existing_shipment = (
            db.query(Shipment)
            .filter(Shipment.order_id == order_id)
            .first()
        )

        if existing_shipment:
            raise HTTPException(
                status_code=409,
                detail="A shipment already exists for this order.",
            )

        shipment = Shipment(
            order_id=order.id,
            courier_name=shipment_data.courier_name.strip(),
            tracking_number=shipment_data.tracking_number.strip(),
            estimated_delivery=shipment_data.estimated_delivery,
            shipment_status="not_shipped",
        )

        db.add(shipment)
        db.commit()
        db.refresh(shipment)

        return {
            "message": "Shipment created successfully.",
            "shipment_id": shipment.id,
            "order_id": shipment.order_id,
            "courier_name": shipment.courier_name,
            "tracking_number": shipment.tracking_number,
            "shipment_status": shipment.shipment_status,
            "estimated_delivery": shipment.estimated_delivery,
        }

    except Exception:
        db.rollback()
        raise


# ---------------------------------------------------------
# 7. UPDATE SHIPMENT STATUS
# ---------------------------------------------------------

@router.patch("/shipments/{shipment_id}")
def update_shipment_status(
    shipment_id: int,
    status_data: ShipmentStatusUpdate,
    _: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    try:
        shipment = (
            db.query(Shipment)
            .filter(Shipment.id == shipment_id)
            .with_for_update()
            .first()
        )

        if shipment is None:
            raise HTTPException(
                status_code=404,
                detail="Shipment not found.",
            )

        order = (
            db.query(Order)
            .filter(Order.id == shipment.order_id)
            .with_for_update()
            .first()
        )

        if order is None:
            raise HTTPException(
                status_code=404,
                detail="Associated order not found.",
            )

        current_status = shipment.shipment_status
        new_status = status_data.shipment_status

        allowed_transitions = {
            "not_shipped": {"shipped"},
            "shipped": {"in_transit", "returned"},
            "in_transit": {"out_for_delivery", "returned"},
            "out_for_delivery": {"delivered", "returned"},
            "delivered": set(),
            "returned": set(),
        }

        if new_status not in allowed_transitions.get(
            current_status, set()
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Cannot change shipment status from "
                    f"{current_status} to {new_status}."
                ),
            )

        now = datetime.now(timezone.utc)

        shipment.shipment_status = new_status

        if new_status == "shipped":
            shipment.shipped_at = now
            order.order_status = "shipped"

        elif new_status in {"in_transit", "out_for_delivery"}:
            order.order_status = "shipped"

        elif new_status == "delivered":
            shipment.delivered_at = now
            order.order_status = "delivered"

        elif new_status == "returned":
            order.order_status = "returned"

        db.commit()
        db.refresh(shipment)

        return {
            "message": "Shipment status updated successfully.",
            "shipment_id": shipment.id,
            "order_id": order.id,
            "order_status": order.order_status,
            "shipment_status": shipment.shipment_status,
            "shipped_at": shipment.shipped_at,
            "delivered_at": shipment.delivered_at,
        }

    except Exception:
        db.rollback()
        raise


# ---------------------------------------------------------
# 8. LIST ALL SHIPMENTS
# ---------------------------------------------------------

@router.get("/shipments")
def list_shipments(
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
        db.query(Shipment)
        .order_by(Shipment.id.desc())
    )

    total = query.count()
    shipments = query.offset(offset).limit(limit).all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "shipments": [
            {
                "shipment_id": shipment.id,
                "order_id": shipment.order_id,
                "courier_name": shipment.courier_name,
                "tracking_number": shipment.tracking_number,
                "shipment_status": shipment.shipment_status,
                "estimated_delivery": shipment.estimated_delivery,
                "shipped_at": shipment.shipped_at,
                "delivered_at": shipment.delivered_at,
            }
            for shipment in shipments
        ],
    }

# ---------------------------------------------------------
# 9. LIST ALL CUSTOMER RETURN REQUESTS
# ---------------------------------------------------------

@router.get("/returns")
def list_return_requests(
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
        db.query(ReturnRequest)
        .options(
            joinedload(ReturnRequest.order),
            joinedload(ReturnRequest.customer),
        )
        .order_by(ReturnRequest.created_at.desc())
    )

    total = query.count()
    requests = query.offset(offset).limit(limit).all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "returns": [
            {
                "return_id": item.id,
                "return_number": item.return_number,
                "order_id": item.order_id,
                "order_number": item.order.order_number,
                "customer_id": item.customer_id,
                "customer_email": item.customer.email,
                "reason": item.reason,
                "comments": item.comments,
                "admin_note": item.admin_note,
                "return_status": item.return_status,
                "created_at": item.created_at,
                "updated_at": item.updated_at,
            }
            for item in requests
        ],
    }


# ---------------------------------------------------------
# 10. APPROVE RETURN REQUEST
# ---------------------------------------------------------

@router.patch("/returns/{return_id}/approve")
def approve_return_request(
    return_id: int,
    _: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    try:
        return_request = (
            db.query(ReturnRequest)
            .filter(ReturnRequest.id == return_id)
            .with_for_update()
            .first()
        )

        if return_request is None:
            raise HTTPException(
                status_code=404,
                detail="Return request not found.",
            )

        if return_request.return_status != "pending_review":
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Cannot approve a return request with "
                    f"status '{return_request.return_status}'."
                ),
            )

        return_request.return_status = "approved"
        return_request.admin_note = None

        db.commit()
        db.refresh(return_request)

        return {
            "message": "Return request approved successfully.",
            "return_id": return_request.id,
            "return_number": return_request.return_number,
            "return_status": return_request.return_status,
            "admin_note": return_request.admin_note,
            "updated_at": return_request.updated_at,
        }

    except Exception:
        db.rollback()
        raise


# ---------------------------------------------------------
# 11. REJECT RETURN REQUEST
# ---------------------------------------------------------

@router.patch("/returns/{return_id}/reject")
def reject_return_request(
    return_id: int,
    request: AdminReturnRejectRequest,
    _: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    try:
        return_request = (
            db.query(ReturnRequest)
            .filter(ReturnRequest.id == return_id)
            .with_for_update()
            .first()
        )

        if return_request is None:
            raise HTTPException(
                status_code=404,
                detail="Return request not found.",
            )

        if return_request.return_status != "pending_review":
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Cannot reject a return request with "
                    f"status '{return_request.return_status}'."
                ),
            )

        rejection_reason = request.reason.strip()

        if len(rejection_reason) < 3:
            raise HTTPException(
                status_code=422,
                detail="Rejection reason must contain at least 3 characters.",
            )

        return_request.return_status = "rejected"
        return_request.admin_note = rejection_reason

        db.commit()
        db.refresh(return_request)

        return {
            "message": "Return request rejected successfully.",
            "return_id": return_request.id,
            "return_number": return_request.return_number,
            "return_status": return_request.return_status,
            "admin_note": return_request.admin_note,
            "updated_at": return_request.updated_at,
        }

    except Exception:
        db.rollback()
        raise


# ---------------------------------------------------------
# 12. COMPLETE RETURN REQUEST
# ---------------------------------------------------------

@router.patch("/returns/{return_id}/complete")
def complete_return_request(
    return_id: int,
    _: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    try:
        return_request = (
            db.query(ReturnRequest)
            .filter(ReturnRequest.id == return_id)
            .with_for_update()
            .first()
        )

        if return_request is None:
            raise HTTPException(
                status_code=404,
                detail="Return request not found.",
            )

        if return_request.return_status != "approved":
            raise HTTPException(
                status_code=409,
                detail=(
                    "Only approved return requests can be completed."
                ),
            )

        return_request.return_status = "completed"

        db.commit()
        db.refresh(return_request)

        return {
            "message": "Return request marked as completed.",
            "return_id": return_request.id,
            "return_number": return_request.return_number,
            "return_status": return_request.return_status,
            "updated_at": return_request.updated_at,
        }

    except Exception:
        db.rollback()
        raise

# ---------------------------------------------------------
# 13. CREATE REFUND FOR COMPLETED RETURN
# ---------------------------------------------------------

@router.post("/returns/{return_id}/refund", status_code=201)
def create_return_refund(
    return_id: int,
    _: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    try:
        return_request = (
            db.query(ReturnRequest)
            .filter(ReturnRequest.id == return_id)
            .with_for_update()
            .first()
        )

        if return_request is None:
            raise HTTPException(status_code=404, detail="Return request not found.")

        if return_request.return_status != "completed":
            raise HTTPException(
                status_code=409,
                detail="Only completed returns can have refunds.",
            )

        existing = db.query(Refund).filter(
            Refund.return_id == return_id
        ).first()

        if existing:
            raise HTTPException(
                status_code=409,
                detail="A refund already exists for this return.",
            )

        order = (
            db.query(Order)
            .filter(Order.id == return_request.order_id)
            .with_for_update()
            .first()
        )

        if order is None:
            raise HTTPException(status_code=404, detail="Original order not found.")

        amount = order.total_amount

        if amount is None or amount <= 0:
            raise HTTPException(
                status_code=409,
                detail="Invalid refund amount.",
            )

        refund = Refund(
            refund_number=f"REF-{uuid4().hex[:12].upper()}",
            return_id=return_request.id,
            order_id=order.id,
            customer_id=return_request.customer_id,
            refund_amount=amount,
            refund_status="pending",
        )

        db.add(refund)
        db.commit()
        db.refresh(refund)

        return {
            "message": "Refund record created successfully.",
            "refund_id": refund.id,
            "refund_number": refund.refund_number,
            "return_id": refund.return_id,
            "order_id": refund.order_id,
            "refund_amount": refund.refund_amount,
            "refund_status": refund.refund_status,
        }

    except Exception:
        db.rollback()
        raise


# ---------------------------------------------------------
# 14. MARK REFUND AS PROCESSED
# ---------------------------------------------------------

@router.patch("/refunds/{refund_id}/process")
def process_refund(
    refund_id: int,
    payment_reference: str,
    _: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    try:
        refund = (
            db.query(Refund)
            .filter(Refund.id == refund_id)
            .with_for_update()
            .first()
        )

        if refund is None:
            raise HTTPException(status_code=404, detail="Refund not found.")

        if refund.refund_status != "pending":
            raise HTTPException(
                status_code=409,
                detail="Only pending refunds can be processed.",
            )

        order = (
            db.query(Order)
            .filter(Order.id == refund.order_id)
            .with_for_update()
            .first()
        )

        if order is None:
            raise HTTPException(status_code=404, detail="Original order not found.")

        if order.payment_status.lower() != "paid":
            raise HTTPException(
                status_code=409,
                detail="Refund cannot be processed because the original order payment is not confirmed as paid.",
            )

        reference = payment_reference.strip()

        if not reference or len(reference) > 150:
            raise HTTPException(
                status_code=422,
                detail="A valid payment reference is required.",
            )

        refund.payment_reference = reference
        refund.refund_status = "processed"

        db.commit()
        db.refresh(refund)

        return {
            "message": "Refund marked as processed.",
            "refund_id": refund.id,
            "refund_number": refund.refund_number,
            "refund_status": refund.refund_status,
            "payment_reference": refund.payment_reference,
        }

    except Exception:
        db.rollback()
        raise


# ---------------------------------------------------------
# 15. MARK REFUND AS FAILED
# ---------------------------------------------------------

@router.patch("/refunds/{refund_id}/fail")
def fail_refund(
    refund_id: int,
    reason: str,
    _: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    try:
        refund = (
            db.query(Refund)
            .filter(Refund.id == refund_id)
            .with_for_update()
            .first()
        )

        if refund is None:
            raise HTTPException(status_code=404, detail="Refund not found.")

        if refund.refund_status != "pending":
            raise HTTPException(
                status_code=409,
                detail="Only pending refunds can be marked as failed.",
            )

        reason = reason.strip()

        if not reason or len(reason) > 1000:
            raise HTTPException(
                status_code=422,
                detail="A valid failure reason is required.",
            )

        refund.refund_status = "failed"
        refund.admin_note = reason

        db.commit()
        db.refresh(refund)

        return {
            "message": "Refund marked as failed.",
            "refund_id": refund.id,
            "refund_number": refund.refund_number,
            "refund_status": refund.refund_status,
            "admin_note": refund.admin_note,
        }

    except Exception:
        db.rollback()
        raise

# ---------------------------------------------------------
# 16. INSPECT RETURN AND RESTORE INVENTORY
# ---------------------------------------------------------

class ReturnInspectionRequest(BaseModel):
    resellable: bool
    note: str | None = Field(default=None, max_length=1000)


@router.patch("/returns/{return_id}/inspect")
def inspect_return(
    return_id: int,
    payload: ReturnInspectionRequest,
    _: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    try:
        return_request = (
            db.query(ReturnRequest)
            .filter(ReturnRequest.id == return_id)
            .with_for_update()
            .first()
        )

        if return_request is None:
            raise HTTPException(status_code=404, detail="Return not found.")

        if return_request.return_status != "completed":
            raise HTTPException(
                status_code=409,
                detail="Only completed returns can be inspected.",
            )

        if return_request.inspection_status != "pending":
            raise HTTPException(
                status_code=409,
                detail="This return has already been inspected.",
            )

        items = (
            db.query(OrderItem)
            .filter(OrderItem.order_id == return_request.order_id)
            .all()
        )

        if not items:
            raise HTTPException(
                status_code=409,
                detail="No order items found for this return.",
            )

        if payload.resellable:
            # Validate all products before changing any stock.
            locked_products = {}

            for item in items:
                product = (
                    db.query(Product)
                    .filter(Product.product_id == item.product_id)
                    .with_for_update()
                    .first()
                )

                if product is None:
                    raise HTTPException(
                        status_code=409,
                        detail=f"Product {item.product_id} not found.",
                    )

                locked_products[item.product_id] = product

            # Restore stock for every returned order item.
            for item in items:
                product = locked_products[item.product_id]
                product.stock_quantity += item.quantity

            return_request.inspection_status = "resellable"
            return_request.restocked_at = datetime.now(timezone.utc)

            message = "Inspection completed. Inventory restored successfully."

        else:
            return_request.inspection_status = "damaged"
            message = "Inspection completed. Damaged products were not restocked."

        if payload.note:
            return_request.admin_note = payload.note

        db.commit()

        return {
            "message": message,
            "return_id": return_request.id,
            "return_number": return_request.return_number,
            "inspection_status": return_request.inspection_status,
            "restocked_at": return_request.restocked_at,
        }

    except Exception:
        db.rollback()
        raise
