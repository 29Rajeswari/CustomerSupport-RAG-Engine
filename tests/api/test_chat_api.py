from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.dependencies import get_current_customer
from app.db.session import get_db


client = TestClient(app)


@pytest.fixture(autouse=True)
def mock_customer_and_database():
    """Provide an authenticated customer and mock database for chat tests."""

    test_customer = SimpleNamespace(id=999)

    mock_db = MagicMock()

    def override_customer():
        return test_customer

    def override_db():
        yield mock_db

    app.dependency_overrides[get_current_customer] = override_customer
    app.dependency_overrides[get_db] = override_db

    yield mock_db

    app.dependency_overrides.clear()


def test_chat_returns_answer_and_sources(mock_customer_and_database):
    """A valid question should return an answer and its sources."""

    mock_result = {
        "answer": (
            "The sample document describes a 12-month warranty. "
            "This is not verified official product policy."
        ),
        "sources": [
            {
                "document_title": "Samsung",
                "version_id": 4,
                "version_number": 1,
                "chunk_id": 1,
            }
        ],
    }

    with patch(
        "app.api.chat.answer_customer_question",
        return_value=mock_result,
    ) as mock_answer:
        response = client.post(
            "/chat",
            json={
                "question": "Does this phone have a one-year warranty?",
                "product_id": "MOB-1001",
            },
        )

    assert response.status_code == 200
    data = response.json()

    assert "12-month warranty" in data["answer"]
    assert len(data["sources"]) == 1
    assert data["sources"][0]["document_title"] == "Samsung"

    mock_answer.assert_called_once()
    mock_customer_and_database.add.assert_any_call(
        pytest.approx(mock_customer_and_database.add.call_args_list[0].args[0])
    )


def test_chat_without_product_id():
    """A question should work when no product ID is supplied."""

    mock_result = {
        "answer": "I could not verify the product-specific warranty.",
        "sources": [],
    }

    with patch(
        "app.api.chat.answer_customer_question",
        return_value=mock_result,
    ) as mock_answer:
        response = client.post(
            "/chat",
            json={
                "question": "What is the warranty period?"
            },
        )

    assert response.status_code == 200
    assert response.json()["sources"] == []

    mock_answer.assert_called_once()


def test_chat_rejects_empty_question():
    """An empty question should fail request validation."""

    response = client.post(
        "/chat",
        json={
            "question": "",
            "product_id": "MOB-1001",
        },
    )

    assert response.status_code == 422


def test_chat_rejects_missing_question():
    """The question field is required."""

    response = client.post(
        "/chat",
        json={
            "product_id": "MOB-1001",
        },
    )

    assert response.status_code == 422


def test_chat_handles_value_error():
    """A service validation error should return HTTP 400."""

    with patch(
        "app.api.chat.answer_customer_question",
        side_effect=ValueError("Question cannot be empty."),
    ):
        response = client.post(
            "/chat",
            json={
                "question": "What is the warranty?",
                "product_id": "MOB-1001",
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Question cannot be empty."


def test_chat_requires_authentication():
    """An unauthenticated request must not access the chatbot."""

    app.dependency_overrides.pop(get_current_customer, None)

    response = client.post(
        "/chat",
        json={"question": "What is the warranty?"},
    )

    assert response.status_code == 401
