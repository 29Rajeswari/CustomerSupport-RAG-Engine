# app\services\mock_courier.py
import asyncio
from datetime import UTC

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.shipment import Shipment
from app.models.shipment_event import ShipmentEvent

COURIER_STEPS = [
    (
        "shipped",
        "Package picked up by the courier.",
        "Seller Warehouse",
    ),
    (
        "in_transit",
        "Package reached the sorting facility.",
        "Regional Sorting Center",
    ),
    (
        "out_for_delivery",
        "Package is out for delivery.",
        "Destination City",
    ),
    (
        "delivered",
        "Package delivered successfully.",
        "Customer Address",
    ),
]


async def simulate_delivery(shipment_id: int):
    for status, description, location in COURIER_STEPS:
        await asyncio.sleep(15)

        db: Session = SessionLocal()

        try:
            shipment = (
                db.query(Shipment)
                .filter(Shipment.id == shipment_id)
                .with_for_update()
                .first()
            )

            if not shipment or shipment.shipment_status != "not_shipped":
                return

            shipment.shipment_status = status

            if status == "delivered":
                shipment.order.order_status = "delivered"

            if status == "shipped" and not shipment.shipped_at:
                from datetime import datetime

                shipment.shipped_at = datetime.now(UTC)

            if status == "delivered":
                from datetime import datetime

                shipment.delivered_at = datetime.now(UTC)

            db.add(
                ShipmentEvent(
                    shipment_id=shipment_id,
                    status=status,
                    description=description,
                    location=location,
                )
            )

            db.commit()

        except Exception:
            db.rollback()
            raise

        finally:
            db.close()
