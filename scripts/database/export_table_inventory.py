from pathlib import Path
from datetime import datetime

from sqlalchemy import text
from app.db.session import engine

backup_dir = Path("storage/backups/database")
backup_dir.mkdir(parents=True, exist_ok=True)

backup_file = backup_dir / (
    f"ecommerce_chatbot_schema_check_{datetime.now():%Y%m%d_%H%M%S}.txt"
)

with engine.connect() as connection:
    tables = connection.execute(
        text("""
            SELECT tablename
            FROM pg_tables
            WHERE schemaname = 'public'
            ORDER BY tablename
        """)
    ).scalars().all()

    with backup_file.open("w", encoding="utf-8") as f:
        f.write("Database: ecommerce_chatbot\n")
        f.write("Public tables:\n")
        for table in tables:
            f.write(f"- {table}\n")

print(f"Table inventory saved to: {backup_file}")
print(f"Tables found: {len(tables)}")
