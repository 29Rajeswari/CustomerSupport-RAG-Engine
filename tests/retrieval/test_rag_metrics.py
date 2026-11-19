import pytest

from app.evaluation.metrics import (
    mean_reciprocal_rank,
    precision_at_k,
    recall_at_k,
)


def test_precision_at_5():
    retrieved = ["C1", "C2", "C3", "C4", "C5"]
    relevant = {"C2", "C4"}

    result = precision_at_k(retrieved, relevant, k=5)

    assert result == 0.4


def test_recall_at_5():
    retrieved = ["C1", "C2", "C3", "C4", "C5"]
    relevant = {"C2", "C4", "C6"}

    result = recall_at_k(retrieved, relevant, k=5)

    assert result == pytest.approx(2 / 3)


def test_mean_reciprocal_rank():
    retrieved = ["C1", "C2", "C3", "C4"]
    relevant = {"C2", "C4"}

    result = mean_reciprocal_rank(retrieved, relevant)

    assert result == 0.5


def test_no_relevant_chunks():
    retrieved = ["C1", "C2", "C3"]
    relevant = {"C5"}

    assert precision_at_k(retrieved, relevant, 3) == 0.0
    assert recall_at_k(retrieved, relevant, 3) == 0.0
    assert mean_reciprocal_rank(retrieved, relevant) == 0.0


def test_empty_relevant_set():
    assert recall_at_k(["C1", "C2"], set(), 2) == 0.0


def test_invalid_k():
    with pytest.raises(ValueError):
        precision_at_k(["C1"], {"C1"}, 0)
