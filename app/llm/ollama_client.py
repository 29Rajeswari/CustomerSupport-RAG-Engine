
# app/llm/ollama_client.py

import ollama

from app.config import settings


def check_ollama_connection() -> bool:
    """Verify that the Ollama server is reachable."""
    client = ollama.Client(host=settings.OLLAMA_BASE_URL)
    client.list()
    return True


def generate_answer(
    prompt: str,
    system_prompt: str = (
        "You are a helpful Indian e-commerce customer support assistant. "
        "Answer only from the supplied evidence. "
        "If the evidence is insufficient, say that you cannot verify the answer."
    ),
) -> str:
    """Generate a response using the configured local chat model."""
    client = ollama.Client(host=settings.OLLAMA_BASE_URL)

    response = client.chat(
        model=settings.OLLAMA_CHAT_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
    )

    return response.message.content.strip()


def generate_embedding(text: str) -> list[float]:
    """Create an embedding using the configured Ollama embedding model."""
    if not text or not text.strip():
        raise ValueError("Cannot create an embedding for empty text.")

    client = ollama.Client(host=settings.OLLAMA_BASE_URL)

    response = client.embed(
        model=settings.OLLAMA_EMBEDDING_MODEL,
        input=text,
    )

    embeddings = response.embeddings

    if not embeddings or not embeddings[0]:
        raise RuntimeError("Ollama returned an empty embedding.")

    return embeddings[0]
