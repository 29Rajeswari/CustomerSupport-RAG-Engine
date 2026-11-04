from sqlalchemy import text
from app.db.session import engine

migration = """
ALTER TABLE document_versions
    ADD COLUMN IF NOT EXISTS file_path VARCHAR(500),
    ADD COLUMN IF NOT EXISTS file_type VARCHAR(20),
    ADD COLUMN IF NOT EXISTS category VARCHAR(100),
    ADD COLUMN IF NOT EXISTS product_id VARCHAR(100);
"""

with engine.begin() as connection:
    connection.execute(text(migration))

print("Migration completed successfully.")
