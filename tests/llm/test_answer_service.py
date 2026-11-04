
from app.db.session import SessionLocal
from app.services.answer_service import answer_customer_question


def main():
    with SessionLocal() as db:
        result = answer_customer_question(
            db=db,
            question="Does this phone have a one-year warranty?",
            product_id="MOB-1001",
            top_k=3,
        )

    print("\nCUSTOMER ANSWER")
    print(result["answer"])

    print("\nSOURCES")
    for source in result["sources"]:
        print(source)


if __name__ == "__main__":
    main()
