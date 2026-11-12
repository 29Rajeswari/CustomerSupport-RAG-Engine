from datetime import datetime, timezone

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base shared by every ORM model."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
