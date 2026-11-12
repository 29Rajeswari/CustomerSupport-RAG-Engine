
from sqlalchemy.orm import Session

from app.models import Order


def _format_datetime(value):
    """Convert a datetime value into an ISO-formatted string."""
    return value.isoformat() if value else None


def _format_order(order: Order) -> dict:
    """Convert an Order database record into a dictionary."""

    shipment = order.shipment

    return {
        "order_id": order.id,
        "order_number": order.order_number,
        "order_status": order.order_status,
        "payment_status": order.payment_status,
        "total_amount": str(order.total_amount),
        "created_at": _format_datetime(order.created_at),

        "items": [
            {
                "product_id": item.product_id,
                "product_name": item.product_name,
                "quantity": item.quantity,
                "unit_price": str(item.unit_price),
                "subtotal": str(item.unit_price * item.quantity),
            }
            for item in order.items
        ],

        "shipment": (
            {
                "courier_name": shipment.courier_name,
                "tracking_number": shipment.tracking_number,
                "shipment_status": shipment.shipment_status,
                "estimated_delivery": _format_datetime(
                    shipment.estimated_delivery
                ),
                "shipped_at": _format_datetime(shipment.shipped_at),
                "delivered_at": _format_datetime(shipment.delivered_at),
            }
            if shipment
            else None
        ),
    }


def get_customer_orders(
    db: Session,
    customer_id: int,
    limit: int = 10,
) -> list[dict]:
    """
    Retrieve orders belonging to one authenticated customer.
    """

    if customer_id <= 0:
        raise ValueError("Invalid customer ID.")

    if not 1 <= limit <= 50:
        raise ValueError("Limit must be between 1 and 50.")

    orders = (
        db.query(Order)
        .filter(Order.customer_id == customer_id)
        .order_by(Order.created_at.desc())
        .limit(limit)
        .all()
    )

    return [_format_order(order) for order in orders]


def get_customer_order_by_number(
    db: Session,
    customer_id: int,
    order_number: str,
) -> dict | None:
    """
    Retrieve a specific order only if it belongs to the customer.
    """

    if customer_id <= 0:
        raise ValueError("Invalid customer ID.")

    if not order_number or not order_number.strip():
        raise ValueError("Order number cannot be empty.")

    order = (
        db.query(Order)
        .filter(
            Order.customer_id == customer_id,
            Order.order_number == order_number.strip().upper(),
        )
        .first()
    )

    if order is None:
        return None

    return _format_order(order)
