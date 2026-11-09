import json
from uuid import uuid4
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.core.dependencies import get_current_customer
from app.db.models import (
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
from app.schemas.order import OrderCreate
from app.schemas.return_request import ReturnRequestCreate

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

# ---------------------------------------------------------
# 5. CREATE CUSTOMER ORDER AND REDUCE INVENTORY
# ---------------------------------------------------------

@router.post("/orders", status_code=status.HTTP_201_CREATED)
def create_customer_order(
    order_data: OrderCreate,
    current_customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    try:
        requested_ids = [
            item.product_id for item in order_data.items
        ]

        # Lock product rows in a consistent order to prevent
        # concurrent purchases from overselling inventory.
        products = (
            db.query(Product)
            .filter(
                Product.product_id.in_(requested_ids),
                Product.is_active.is_(True),
            )
            .order_by(Product.product_id)
            .with_for_update()
            .all()
        )

        products_by_id = {
            product.product_id: product for product in products
        }

        # Validate product existence and available stock.
        for requested_item in order_data.items:
            product = products_by_id.get(requested_item.product_id)

            if product is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=(
                        f"Product {requested_item.product_id} "
                        "was not found or is inactive."
                    ),
                )

            if product.stock_quantity < requested_item.quantity:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "message": "Insufficient product stock.",
                        "product_id": product.product_id,
                        "available_stock": product.stock_quantity,
                        "requested_quantity": requested_item.quantity,
                    },
                )

        # Calculate the order total using database prices.
        total_amount = sum(
            (
                products_by_id[item.product_id].price
                * item.quantity
                for item in order_data.items
            ),
            Decimal("0.00"),
        )

        # Create the order.
        order = Order(
            order_number=f"ORD-{uuid4().hex[:12].upper()}",
            customer_id=current_customer.id,
            total_amount=total_amount,
        )

        db.add(order)
        db.flush()

        response_items = []

        # Create order items and reduce inventory.
        for requested_item in order_data.items:
            product = products_by_id[requested_item.product_id]

            product.stock_quantity -= requested_item.quantity

            order_item = OrderItem(
                order_id=order.id,
                product_id=product.product_id,
                product_name=product.product_name,
                quantity=requested_item.quantity,
                unit_price=product.price,
            )

            db.add(order_item)

            response_items.append({
                "product_id": product.product_id,
                "product_name": product.product_name,
                "quantity": requested_item.quantity,
                "unit_price": product.price,
                "subtotal": (
                    product.price * requested_item.quantity
                ),
                "remaining_stock": product.stock_quantity,
            })

        # Commit order, order items and stock changes together.
        db.commit()
        db.refresh(order)

        return {
            "message": "Order placed successfully.",
            "order_id": order.id,
            "order_number": order.order_number,
            "order_status": order.order_status,
            "payment_status": order.payment_status,
            "total_amount": order.total_amount,
            "products": response_items,
        }

    except Exception:
        db.rollback()
        raise


# ---------------------------------------------------------
# 6. CANCEL CUSTOMER ORDER AND RESTORE INVENTORY
# ---------------------------------------------------------

@router.post("/orders/{order_id}/cancel")
def cancel_customer_order(
    order_id: int,
    current_customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    try:
        # Lock the order to prevent concurrent cancellation.
        order = (
            db.query(Order)
            .filter(
                Order.id == order_id,
                Order.customer_id == current_customer.id,
            )
            .with_for_update()
            .first()
        )

        if order is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found.",
            )

        # Prevent cancelling the same order more than once.
        if order.order_status == "cancelled":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This order has already been cancelled.",
            )

        # Only processing orders can be cancelled.
        if order.order_status != "processing":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Only processing orders can be cancelled.",
            )

        # This version supports unpaid orders only.
        if order.payment_status != "pending":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Only orders with pending payment can be cancelled.",
            )

        # Check shipment status.
        shipment = order.shipment

        if shipment and shipment.shipment_status != "not_shipped":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This order can no longer be cancelled because shipment has started.",
            )

        # Load purchased items.
        order_items = (
            db.query(OrderItem)
            .filter(OrderItem.order_id == order.id)
            .order_by(OrderItem.product_id)
            .all()
        )

        if not order_items:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No order items were found.",
            )

        # Lock all corresponding products in a consistent order.
        product_ids = sorted({
            item.product_id for item in order_items
        })

        products = (
            db.query(Product)
            .filter(Product.product_id.in_(product_ids))
            .order_by(Product.product_id)
            .with_for_update()
            .all()
        )

        products_by_id = {
            product.product_id: product
            for product in products
        }

        # Do not cancel if any product record is missing.
        for item in order_items:
            if item.product_id not in products_by_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Cannot restore inventory: "
                        f"product {item.product_id} was not found."
                    ),
                )

        # Restore the purchased quantities.
        restored_items = []

        for item in order_items:
            product = products_by_id[item.product_id]

            product.stock_quantity += item.quantity

            restored_items.append({
                "product_id": product.product_id,
                "product_name": product.product_name,
                "restored_quantity": item.quantity,
                "available_stock": product.stock_quantity,
            })

        # Mark the order as cancelled.
        order.order_status = "cancelled"

        # Commit cancellation and inventory restoration together.
        db.commit()
        db.refresh(order)

        return {
            "message": "Order cancelled successfully.",
            "order_id": order.id,
            "order_number": order.order_number,
            "order_status": order.order_status,
            "restored_products": restored_items,
        }

    except Exception:
        db.rollback()
        raise



# ---------------------------------------------------------
# 7. CUSTOMER ORDER TRACKING
# ---------------------------------------------------------

@router.get("/orders/{order_id}/tracking")
def track_customer_order(
    order_id: int,
    current_customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    order = (
        db.query(Order)
        .options(joinedload(Order.shipment))
        .filter(
            Order.id == order_id,
            Order.customer_id == current_customer.id,
        )
        .first()
    )

    if order is None:
        raise HTTPException(
            status_code=404,
            detail="Order not found.",
        )

    shipment = order.shipment

    if shipment is None:
        raise HTTPException(
            status_code=404,
            detail="Shipment has not been created for this order yet.",
        )

    return {
        "order_id": order.id,
        "order_number": order.order_number,
        "order_status": order.order_status,
        "shipment": {
            "courier_name": shipment.courier_name,
            "tracking_number": shipment.tracking_number,
            "shipment_status": shipment.shipment_status,
            "estimated_delivery": shipment.estimated_delivery,
            "shipped_at": shipment.shipped_at,
            "delivered_at": shipment.delivered_at,
        },
    }

# ---------------------------------------------------------
# 8. CUSTOMER RETURN REQUESTS
# ---------------------------------------------------------

@router.post(
    "/orders/{order_id}/returns",
    status_code=status.HTTP_201_CREATED,
)
def create_return_request(
    order_id: int,
    request: ReturnRequestCreate,
    current_customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    # 1. Find the order belonging to the logged-in customer.
    order = (
        db.query(Order)
        .filter(
            Order.id == order_id,
            Order.customer_id == current_customer.id,
        )
        .first()
    )

    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found.",
        )

    # 2. Only delivered orders can currently be submitted.
    if order.order_status.lower() != "delivered":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Return requests can only be submitted for delivered orders.",
        )

    # 3. Prevent another active return request for this order.
    existing_request = (
        db.query(ReturnRequest)
        .filter(
            ReturnRequest.order_id == order_id,
            ReturnRequest.customer_id == current_customer.id,
            ReturnRequest.return_status.in_(
                ["pending_review", "approved"]
            ),
        )
        .first()
    )

    if existing_request:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An active return request already exists for this order.",
        )

    # 4. Generate a unique return number.
    return_number = f"RET-{uuid4().hex[:12].upper()}"

    # 5. Create the return request.
    return_request = ReturnRequest(
        return_number=return_number,
        order_id=order.id,
        customer_id=current_customer.id,
        reason=request.reason.strip(),
        comments=(
            request.comments.strip()
            if request.comments and request.comments.strip()
            else None
        ),
        return_status="pending_review",
    )

    try:
        db.add(return_request)
        db.commit()
        db.refresh(return_request)

    except Exception:
        db.rollback()
        raise

    return {
        "message": "Return request submitted successfully.",
        "return_id": return_request.id,
        "return_number": return_request.return_number,
        "order_id": return_request.order_id,
        "order_number": order.order_number,
        "reason": return_request.reason,
        "comments": return_request.comments,
        "return_status": return_request.return_status,
        "created_at": return_request.created_at,
    }


# ---------------------------------------------------------
# 9. VIEW CUSTOMER RETURN REQUESTS
# ---------------------------------------------------------

@router.get("/returns")
def get_customer_return_requests(
    current_customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    return_requests = (
        db.query(ReturnRequest)
        .filter(
            ReturnRequest.customer_id == current_customer.id
        )
        .order_by(ReturnRequest.created_at.desc())
        .all()
    )

    return {
        "total": len(return_requests),
        "returns": [
            {
                "return_id": item.id,
                "return_number": item.return_number,
                "order_id": item.order_id,
                "reason": item.reason,
                "comments": item.comments,
                "return_status": item.return_status,
                "created_at": item.created_at,
                "updated_at": item.updated_at,
            }
            for item in return_requests
        ],
    }


# ---------------------------------------------------------
# 10. VIEW SINGLE CUSTOMER RETURN REQUEST
# ---------------------------------------------------------

@router.get("/returns/{return_number}")
def get_customer_return_request(
    return_number: str,
    current_customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    return_request = (
        db.query(ReturnRequest)
        .filter(
            ReturnRequest.return_number == return_number,
            ReturnRequest.customer_id == current_customer.id,
        )
        .first()
    )

    if return_request is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Return request not found.",
        )

    return {
        "return_id": return_request.id,
        "return_number": return_request.return_number,
        "order_id": return_request.order_id,
        "reason": return_request.reason,
        "comments": return_request.comments,
        "return_status": return_request.return_status,
        "created_at": return_request.created_at,
        "updated_at": return_request.updated_at,
    }

# ---------------------------------------------------------
# 11. CUSTOMER REFUND HISTORY
# ---------------------------------------------------------

@router.get("/refunds")
def get_customer_refunds(
    current_customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    refunds = (
        db.query(Refund)
        .filter(Refund.customer_id == current_customer.id)
        .order_by(Refund.created_at.desc())
        .all()
    )

    return {
        "total": len(refunds),
        "refunds": [
            {
                "refund_id": item.id,
                "refund_number": item.refund_number,
                "return_id": item.return_id,
                "order_id": item.order_id,
                "refund_amount": str(item.refund_amount),
                "refund_status": item.refund_status,
                "payment_reference": item.payment_reference,
                "admin_note": item.admin_note,
                "created_at": item.created_at,
                "updated_at": item.updated_at,
            }
            for item in refunds
        ],
    }