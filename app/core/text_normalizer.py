
# app/core/text_normalizer.py

import re
import unicodedata


# Common number words used in customer questions and product documents.
NUMBER_WORDS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}

# Convert these common expressions into canonical duration formats.
SPECIAL_EXPRESSIONS = [
    (r"\bhalf\s+a\s+decade\b", "60 months"),
    (r"\bhalf\s+decade\b", "60 months"),
    (r"\ba\s+decade\b", "120 months"),
    (r"\bone\s+decade\b", "120 months"),
    (r"\bhalf\s+a\s+century\b", "600 months"),
    (r"\bhalf\s+a\s+year\b", "6 months"),
    (r"\bhalf\s+year\b", "6 months"),
    (r"\bone\s+year\b", "12 months"),
    (r"\ba\s+year\b", "12 months"),
    (r"\bone\s+month\b", "1 month"),
    (r"\bone\s+week\b", "7 days"),
    (r"\bone\s+day\b", "1 day"),
    (r"\ba\s+dozen\b", "12"),
    (r"\bone\s+dozen\b", "12"),
]

# Recognize numerical durations written as words or digits.
DURATION_UNITS = {
    "year": 12,
    "years": 12,
    "yr": 12,
    "yrs": 12,
    "month": 1,
    "months": 1,
    "week": 7 / 30,
    "weeks": 7 / 30,
    "day": 1 / 30,
    "days": 1 / 30,
}

# Longer expressions are normalized before shorter expressions.
SPECIAL_EXPRESSIONS.sort(
    key=lambda item: len(item[0]),
    reverse=True,
)


def _number_word_to_digits(match: re.Match) -> str:
    """Convert recognized number words to digits."""
    word = match.group(0).lower()
    return str(NUMBER_WORDS.get(word, word))


def normalize_text(text: str) -> str:
    """
    Normalize text for search without deciding the meaning of a policy.

    Examples:
        "A dozen products" -> "12 products"
        "ONE YEAR warranty" -> "12 months warranty"
        "half a year" -> "6 months"

    The caller should preserve the original text separately.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string")

    # Normalize Unicode and whitespace.
    normalized = unicodedata.normalize("NFKC", text)
    normalized = normalized.replace("\u2019", "'")
    normalized = re.sub(r"\s+", " ", normalized).strip()

    # Normalize common expressions before converting individual words.
    for pattern, replacement in SPECIAL_EXPRESSIONS:
        normalized = re.sub(
            pattern,
            replacement,
            normalized,
            flags=re.IGNORECASE,
        )

    # Convert number words when they directly precede a duration unit.
    # Examples: "six months" -> "6 months", "two years" -> "2 years".
    number_pattern = "|".join(
        sorted(NUMBER_WORDS.keys(), key=len, reverse=True)
    )

    duration_pattern = (
        r"\b(" + number_pattern + r")\s+"
        r"(years?|yrs?|months?|weeks?|days?)\b"
    )

    def replace_duration(match: re.Match) -> str:
        number = NUMBER_WORDS[match.group(1).lower()]
        unit = match.group(2).lower()

        # Standardize common abbreviations and singular/plural forms.
        if unit in ("year", "years", "yr", "yrs"):
            unit = "year" if number == 1 else "years"
        elif unit in ("month", "months"):
            unit = "month" if number == 1 else "months"
        elif unit in ("week", "weeks"):
            unit = "week" if number == 1 else "weeks"
        else:
            unit = "day" if number == 1 else "days"

        return f"{number} {unit}"

    normalized = re.sub(
        duration_pattern,
        replace_duration,
        normalized,
        flags=re.IGNORECASE,
    )
    # Remove an unnecessary article before a numeric duration.
    # Example: "a six months warranty" -> "6 months warranty"
    normalized = re.sub(
        r"\ba\s+(?=\d+\s+(?:years?|yrs?|months?|weeks?|days?)\b)",
        "",
        normalized,
        flags=re.IGNORECASE,
    )

    # Convert standalone number words only in common quantity contexts.
    normalized = re.sub(
        r"\b(" + number_pattern + r")\b(?=\s+(?:products?|items?|pieces?|units?))",
        _number_word_to_digits,
        normalized,
        flags=re.IGNORECASE,
    )

    # Case-fold for case-insensitive text search.
    normalized = normalized.casefold()

    # Clean repeated spaces introduced by replacements.
    normalized = re.sub(r"\s+", " ", normalized).strip()

    return normalized


def normalize_query(text: str) -> str:
    """
    Normalize a customer question for retrieval.

    This function deliberately preserves question words and negation.
    Do not use its output as a replacement for the original question
    when generating the final customer-facing answer.
    """
    return normalize_text(text)
