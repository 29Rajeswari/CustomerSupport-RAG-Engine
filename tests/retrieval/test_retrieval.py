
from unittest.mock import patch

from sqlalchemy import select

from app.models import Document, DocumentChunk, DocumentVersion
from app.db.session import SessionLocal
from app.retrieval.search import search_relevant_chunks


def test_product_001_active_policy():
    """Product 001 must retrieve only its active documents."""

    with SessionLocal() as db:
        with patch(
            "app.retrieval.search.generate_embedding",
            return_value=[0.0] * 768,
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


def test_product_002_latest_policy():
    """Product 002 must not retrieve superseded policies."""

    with SessionLocal() as db:
        with patch(
            "app.retrieval.search.generate_embedding",
            return_value=[0.0] * 768,
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
            assert result["document_title"] == (
                "Cross Document Warranty Test"
            )
            assert result["version_number"] == 4


def test_superseded_versions_are_excluded():
    """Retrieved chunks must belong to active versions only."""

    with SessionLocal() as db:
        with patch(
            "app.retrieval.search.generate_embedding",
            return_value=[0.0] * 768,
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


def test_different_product_isolation():
    """A nonexistent product must not return another product's chunks."""

    with SessionLocal() as db:
        with patch(
            "app.retrieval.search.generate_embedding",
            return_value=[0.0] * 768,
        ):
            results = search_relevant_chunks(
                db=db,
                question="What is the warranty?",
                product_id="NONEXISTENT-TEST-PRODUCT",
                category="warranty",
            )

        assert results == []


def test_empty_question():
    """Empty questions must be rejected."""

    with SessionLocal() as db:
        try:
            search_relevant_chunks(
                db=db,
                question="",
                product_id="001",
            )
        except ValueError as exc:
            assert "empty" in str(exc).lower()
        else:
            raise AssertionError(
                "Empty question was not rejected"
            )
