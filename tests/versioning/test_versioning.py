
# tests/test_versioning.py

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, Document, DocumentVersion
from app.ingestion.versioning import (
    create_document_version,
    get_active_version,
)


@pytest.fixture
def db_session():
    """Create an isolated in-memory SQLite database for unit tests."""
    engine = create_engine("sqlite:///:memory:")

    # SQLite cannot create PostgreSQL's vector column directly.
    # These tests use a temporary SQLite engine only for the
    # document-versioning tables, which do not need embeddings.
    from sqlalchemy import JSON
    from sqlalchemy.dialects.postgresql import JSONB

    # Create the required tables only, excluding document_chunks.
    Document.__table__.create(engine)
    DocumentVersion.__table__.create(engine)

    TestingSession = sessionmaker(bind=engine)

    with TestingSession() as session:
        yield session

    engine.dispose()


def test_create_first_document_version(db_session):
    document = Document(
        title="Mixer Grinder Warranty",
        category="warranty",
        file_path="storage/uploads/warranty.txt",
        file_type="txt",
    )
    db_session.add(document)
    db_session.flush()

    version = create_document_version(db_session, document)
    db_session.commit()

    assert version.version_number == 1
    assert version.is_active is False
    assert version.status == "processing"


def test_create_second_document_version(db_session):
    document = Document(
        title="Mixer Grinder Warranty",
        category="warranty",
        file_path="storage/uploads/warranty.txt",
        file_type="txt",
    )
    db_session.add(document)
    db_session.flush()

    first = create_document_version(db_session, document)
    db_session.commit()

    second = create_document_version(db_session, document)
    db_session.commit()

    assert first.version_number == 1
    assert second.version_number == 2


def test_get_active_version_returns_none_initially(db_session):
    document = Document(
        title="Return Policy",
        category="returns",
        file_path="storage/uploads/returns.txt",
        file_type="txt",
    )
    db_session.add(document)
    db_session.flush()

    version = create_document_version(db_session, document)
    db_session.commit()

    assert get_active_version(db_session, document.id) is None
    assert version.is_active is False
