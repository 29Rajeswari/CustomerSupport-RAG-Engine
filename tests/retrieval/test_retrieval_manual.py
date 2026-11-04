
from app.db.session import SessionLocal
from app.retrieval.search import search_relevant_chunks


def main():
    with SessionLocal() as db:
        results = search_relevant_chunks(
            db=db,
            question="Does this phone have a one-year warranty?",
            product_id="MOB-1001",
            top_k=3,
        )

        if not results:
            print("No matching active document chunks were found.")
            return

        for index, result in enumerate(results, start=1):
            print(f"\nResult {index}")
            print("Document:", result["document_title"])
            print("Version:", result["version_number"])
            print("Category:", result["category"])
            print("Distance:", round(result["distance"], 4))
            print("Content:", result["content"])


if __name__ == "__main__":
    main()
