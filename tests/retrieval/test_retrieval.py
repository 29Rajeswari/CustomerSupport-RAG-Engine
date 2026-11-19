from unittest.mock import patch

import pytest

from app.db.models import Document, DocumentChunk, DocumentVersion
from app.db.session import SessionLocal, engine
from app.retrieval.search import search_relevant_chunks


@pytest.fixture
def db():
    """
    Create an isolated database transaction for each test.

    All test records are rolled back after the test finishes.
    Existing database records are not modified.
    """
    connection = engine.connect()
    transaction = connection.begin()

    session = SessionLocal(bind=connection)

    try:
        # Create Product 001 test data.
        product_001 = Document(
            title="Product 001 Warranty Test",
            category="warranty",
            product_id="001",
            file_path="tests/fixtures/product001.txt",
            file_type="txt",
            status="active",
        )

        session.add(product_001)
        session.flush()

        version_001 = DocumentVersion(
            document_id=product_001.id,
            version_number=1,
            product_id="001",
            category="warranty",
            status="active",
            is_active=True,
        )

        session.add(version_001)
        session.flush()

        chunk_001 = DocumentChunk(
            version_id=version_001.id,
            chunk_index=0,
            content="Product 001 has a 12-month warranty.",
            product_id="001",
            category="warranty",
            embedding=[1.0] + [0.0] * 767,
        )

        session.add(chunk_001)

        # Create Product 002 test data.
        product_002 = Document(
            title="Cross Document Warranty Test",
            category="warranty",
            product_id="002",
            file_path="tests/fixtures/product002.txt",
            file_type="txt",
            status="active",
        )

        session.add(product_002)
        session.flush()

        # Create historical superseded versions 1, 2 and 3.
        for version_number in range(1, 4):
            old_version = DocumentVersion(
                document_id=product_002.id,
                version_number=version_number,
                product_id="002",
                category="warranty",
                status="superseded",
                is_active=False,
            )

            session.add(old_version)
            session.flush()

            old_chunk = DocumentChunk(
                version_id=old_version.id,
                chunk_index=0,
                content=f"Old warranty policy version {version_number}.",
                product_id="002",
                category="warranty",
                embedding=[1.0] + [0.0] * 767,
            )

            session.add(old_chunk)

        # Create the latest active version 4.
        latest_version = DocumentVersion(
            document_id=product_002.id,
            version_number=4,
            product_id="002",
            category="warranty",
            status="active",
            is_active=True,
        )

        session.add(latest_version)
        session.flush()

        latest_chunk = DocumentChunk(
            version_id=latest_version.id,
            chunk_index=0,
            content="Product 002 has a 24-month warranty.",
            product_id="002",
            category="warranty",
            embedding=[1.0] + [0.0] * 767,
        )

        session.add(latest_chunk)

        # Make all fixture records visible to retrieval queries.
        session.flush()

        yield session

    finally:
        session.close()
        transaction.rollback()
        connection.close()


def test_product_001_active_policy(db):
    """Product 001 must retrieve only its active documents."""

    with patch(
        "app.retrieval.search.generate_embedding",
        return_value=[1.0] + [0.0] * 767,
    ):
        results = search_relevant_chunks(
            db=db,
            question="What is the warranty period?",
            product_id="001",
            category="warranty",
        )

    assert results, "No active warranty chunks found for 001"

    for result in results:
        assert result["product_id"] == "001"

        version = db.get(
            DocumentVersion,
            result["version_id"],
        )

        assert version is not None
        assert version.is_active is True
        assert version.status == "active"


def test_product_002_latest_policy(db):
    """Product 002 must not retrieve superseded policies."""

    with patch(
        "app.retrieval.search.generate_embedding",
        return_value=[1.0] + [0.0] * 767,
    ):
        results = search_relevant_chunks(
            db=db,
            question="What is the warranty period?",
            product_id="002",
            category="warranty",
        )

    assert results, "No active warranty chunks found for 002"

    for result in results:
        assert result["product_id"] == "002"
        assert result["document_title"] == "Cross Document Warranty Test"
        assert result["version_number"] == 4


def test_superseded_versions_are_excluded(db):
    """Retrieved chunks must belong to active versions only."""

    with patch(
        "app.retrieval.search.generate_embedding",
        return_value=[1.0] + [0.0] * 767,
    ):
        results = search_relevant_chunks(
            db=db,
            question="Warranty information",
            product_id="002",
            category="warranty",
        )

    for result in results:
        version = db.get(
            DocumentVersion,
            result["version_id"],
        )

        document = db.get(
            Document,
            result["document_id"],
        )

        assert version is not None
        assert document is not None
        assert version.is_active is True
        assert version.status == "active"
        assert document.status == "active"


def test_different_product_isolation(db):
    """A nonexistent product must not return another product's chunks."""

    with patch(
        "app.retrieval.search.generate_embedding",
        return_value=[1.0] + [0.0] * 767,
    ):
        results = search_relevant_chunks(
            db=db,
            question="What is the warranty?",
            product_id="NONEXISTENT-TEST-PRODUCT",
            category="warranty",
        )

    assert results == []


def test_empty_question(db):
    """Empty questions must be rejected."""

    with pytest.raises(ValueError, match="empty"):
        search_relevant_chunks(
            db=db,
            question="",
            product_id="001",
        )
