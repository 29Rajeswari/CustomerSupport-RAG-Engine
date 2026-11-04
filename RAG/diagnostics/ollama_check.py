
# test_ollama.py

from app.llm.ollama_client import (
    check_ollama_connection,
    generate_answer,
    generate_embedding,
)


def main():
    print("Checking Ollama connection...")

    check_ollama_connection()
    print("SUCCESS: Ollama server is reachable.")

    print("\nTesting chat model...")

    answer = generate_answer(
        "The product has a 12-month manufacturer's warranty. "
        "How long is the warranty?"
    )
    print("Chat answer:", answer)

    print("\nTesting embedding model...")

    vector = generate_embedding(
        "The mixer grinder has a 12-month warranty."
    )

    print("Embedding dimensions:", len(vector))

    assert len(vector) == 768, (
        f"Expected 768 dimensions, received {len(vector)}."
    )

    print("SUCCESS: Ollama chat and embeddings are working.")


if __name__ == "__main__":
    main()
