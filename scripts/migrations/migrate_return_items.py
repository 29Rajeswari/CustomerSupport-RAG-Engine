from sqlalchemy import text
from app.db.session import engine

migration = """
CREATE TABLE IF NOT EXISTS return_items (
    id SERIAL PRIMARY KEY,
    return_id INTEGER NOT NULL
        REFERENCES return_requests(id) ON DELETE CASCADE,
    order_item_id INTEGER NOT NULL
        REFERENCES order_items(id) ON DELETE RESTRICT,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_return_items_return_order_item
        UNIQUE (return_id, order_item_id)
);
"""

with engine.begin() as connection:
    connection.execute(text(migration))

print("Return items migration completed successfully.")