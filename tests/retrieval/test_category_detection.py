
from app.services.answer_service import detect_category


def test_warranty_questions():
    assert detect_category("What is the warranty period?") == "warranty"
    assert detect_category("Does this product have a guarantee?") == "warranty"


def test_return_questions():
    assert detect_category("Can I return this product?") == "return"
    assert detect_category("How do I get my money back?") == "return"


def test_exchange_questions():
    assert detect_category("Can I exchange this product?") == "exchange"
    assert detect_category("Can I replace my product?") == "exchange"


def test_delivery_questions():
    assert detect_category("When will my order arrive?") == "delivery"
    assert detect_category("How can I track my shipment?") == "delivery"


def test_unrecognized_question():
    assert detect_category("Tell me about this product") is None
