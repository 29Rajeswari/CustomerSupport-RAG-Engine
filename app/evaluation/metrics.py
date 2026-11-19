def precision_at_k(retrieved_ids, relevant_ids, k=5):
    """Calculate Precision@K."""

    if k <= 0:
        raise ValueError("k must be greater than zero")

    relevant = set(relevant_ids)
    retrieved = retrieved_ids[:k]

    hits = len(set(retrieved) & relevant)

    return hits / k


def recall_at_k(retrieved_ids, relevant_ids, k=5):
    """Calculate Recall@K."""

    if k <= 0:
        raise ValueError("k must be greater than zero")

    relevant = set(relevant_ids)

    if not relevant:
        return 0.0

    retrieved = set(retrieved_ids[:k])

    hits = len(retrieved & relevant)

    return hits / len(relevant)


def mean_reciprocal_rank(retrieved_ids, relevant_ids):
    """Calculate Reciprocal Rank for one query."""

    relevant = set(relevant_ids)

    for rank, chunk_id in enumerate(retrieved_ids, start=1):
        if chunk_id in relevant:
            return 1 / rank

    return 0.0
