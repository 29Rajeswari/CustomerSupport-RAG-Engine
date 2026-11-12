
# create_tables.py

from sqlalchemy import text

from app.models import Base
from app.db.session import engine


def create_tables() -> None:
    """Create missing tables and verify the pgvector extension."""
    with engine.begin() as connection:
        connection.execute(
            text("CREATE EXTENSION IF NOT EXISTS vector")
        )

    Base.metadata.create_all(bind=engine)
    print("SUCCESS: Database tables created or already exist.")


if __name__ == "__main__":
    create_tables()
