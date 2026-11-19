
from sqlalchemy import text
from app.db.session import engine

migration = """
CREATE TABLE IF NOT EXISTS shipment_events (
    id SERIAL PRIMARY KEY,
    shipment_id INTEGER NOT NULL
        REFERENCES shipments(id) ON DELETE CASCADE,
    status VARCHAR(30) NOT NULL,
    description TEXT,
    location VARCHAR(150),
    created_at TIMESTAMP WITH TIME ZONE
        NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_shipment_events_shipment_id
ON shipment_events(shipment_id);
"""

with engine.begin() as connection:
    for statement in migration.split(";"):
        if statement.strip():
            connection.execute(text(statement))

print("Shipment events migration completed successfully.")
