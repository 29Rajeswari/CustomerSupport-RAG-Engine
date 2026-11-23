"""Ground-truth dataset for Phase 2 RAG generation evaluation.

Reference answers are derived from the sample policy documents used in the
inspection database. They are test references, not official manufacturer/store
policy statements.
"""

EVALUATION_DATASET = [
    {
        "id": "Q01",
        "question": "How many months of warranty does the Galaxy A15 have?",
        "product_id": "MOB-1001",
        "category": "warranty",
        "reference_answer": "The Galaxy A15 sample policy provides a 12-month warranty from the date of purchase.",
    },
    {
        "id": "Q02",
        "question": "When does the smartphone warranty begin?",
        "product_id": "MOB-1001",
        "category": "warranty",
        "reference_answer": "The warranty period begins on the date of purchase.",
    },
    {
        "id": "Q03",
        "question": "What type of defects are covered under the warranty?",
        "product_id": "MOB-1001",
        "category": "warranty",
        "reference_answer": "The policy covers manufacturing defects in smartphone hardware under normal use.",
    },
    {
        "id": "Q04",
        "question": "Does the warranty cover manufacturing defects?",
        "product_id": "MOB-1001",
        "category": "warranty",
        "reference_answer": "Yes. Manufacturing defects in smartphone hardware are covered under normal use.",
    },
    {
        "id": "Q05",
        "question": "What proof is required to request warranty service?",
        "product_id": "MOB-1001",
        "category": "warranty",
        "reference_answer": "Valid proof of purchase and the product serial number are required for a warranty claim.",
    },
    {
        "id": "Q06",
        "question": "Do I need the product serial number for a warranty claim?",
        "product_id": "MOB-1001",
        "category": "warranty",
        "reference_answer": "Yes. The product serial number is required, along with valid proof of purchase.",
    },
    {
        "id": "Q07",
        "question": "Is accidental damage covered by the warranty?",
        "product_id": "MOB-1001",
        "category": "warranty",
        "reference_answer": "No. Accidental damage is excluded from the sample warranty policy.",
    },
    {
        "id": "Q08",
        "question": "Does liquid damage qualify for warranty service?",
        "product_id": "MOB-1001",
        "category": "warranty",
        "reference_answer": "No. Liquid damage is excluded from the sample warranty policy.",
    },
    {
        "id": "Q09",
        "question": "Are unauthorized repairs covered?",
        "product_id": "MOB-1001",
        "category": "warranty",
        "reference_answer": "No. Damage or issues involving unauthorized repairs are excluded from the warranty.",
    },
    {
        "id": "Q10",
        "question": "What information should I provide when contacting support about a warranty issue?",
        "product_id": "MOB-1001",
        "category": "warranty",
        "reference_answer": "Provide the order number, purchase date, product serial number, and a description of the issue.",
    },
    {
        "id": "Q11",
        "question": "Is a replacement guaranteed when a warranty claim is approved?",
        "product_id": "MOB-1001",
        "category": "warranty",
        "reference_answer": "No. A replacement is not guaranteed in every case. An approved claim may result in repair or replacement.",
    },
    {
        "id": "Q12",
        "question": "What happens after a warranty claim is approved?",
        "product_id": "MOB-1001",
        "category": "warranty",
        "reference_answer": "After approval, the product may be repaired or replaced, depending on the applicable policy terms.",
    },
    {
        "id": "Q13",
        "question": "How is the warranty expiry date calculated in the example policy?",
        "product_id": "MOB-1001",
        "category": "warranty",
        "reference_answer": (
            "The example policy calculates expiry by adding 12 months "
            "to the purchase date. For a purchase on 15 January 2026, "
            "the warranty expires on 15 January 2027."
        ),
    },
]