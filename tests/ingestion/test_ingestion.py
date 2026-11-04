import pytest
from docx import Document as WordDocument
from openpyxl import Workbook

from app.ingestion.parsers import (
    DocumentParsingError,
    extract_text,
)


def test_extract_text_file(tmp_path):
    path = tmp_path / "warranty.txt"
    path.write_text(
        "Mixer grinder warranty: 12 months from purchase.",
        encoding="utf-8",
    )

    result = extract_text(path)

    assert "12 months" in result
    assert "warranty" in result.lower()


def test_extract_word_document(tmp_path):
    path = tmp_path / "product.docx"

    document = WordDocument()
    document.add_paragraph(
        "Prestige mixer grinder has a 12-month warranty."
    )

    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Warranty"
    table.cell(0, 1).text = "12 months"

    document.save(path)

    result = extract_text(path)

    assert "Prestige mixer grinder" in result
    assert "Warranty" in result
    assert "12 months" in result


def test_extract_excel_document(tmp_path):
    path = tmp_path / "products.xlsx"

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Products"

    worksheet.append(["Product", "Warranty"])
    worksheet.append(["Mixer grinder", "12 months"])

    workbook.save(path)

    result = extract_text(path)

    assert "Products" in result
    assert "Mixer grinder" in result
    assert "12 months" in result


def test_missing_file_raises_error(tmp_path):
    with pytest.raises(DocumentParsingError, match="File not found"):
        extract_text(tmp_path / "missing.txt")


def test_unsupported_file_raises_error(tmp_path):
    path = tmp_path / "document.csv"
    path.write_text("product,warranty", encoding="utf-8")

    with pytest.raises(
        DocumentParsingError,
        match="Unsupported file type",
    ):
        extract_text(path)


def test_empty_text_file_raises_error(tmp_path):
    path = tmp_path / "empty.txt"
    path.write_text("", encoding="utf-8")

    with pytest.raises(
        DocumentParsingError,
        match="No readable text",
    ):
        extract_text(path)

from app.ingestion.processor import split_into_chunks


def test_split_into_chunks_empty_text():
    assert split_into_chunks("") == []


def test_split_into_chunks_short_text():
    text = "Warranty coverage is 12 months."

    assert split_into_chunks(text) == [text]


def test_split_into_chunks_creates_multiple_chunks():
    text = " ".join(["warranty"] * 500)

    chunks = split_into_chunks(
        text,
        chunk_size=200,
        overlap=40,
    )

    assert len(chunks) > 1
    assert all(chunks)
    assert all(len(chunk) <= 200 for chunk in chunks)


def test_split_into_chunks_preserves_overlap():
    text = " ".join(f"word{i}" for i in range(100))

    chunks = split_into_chunks(
        text,
        chunk_size=100,
        overlap=20,
    )

    assert len(chunks) > 1

    # At least some content should be shared by adjacent chunks.
    assert any(
        set(chunks[i].split()) & set(chunks[i + 1].split())
        for i in range(len(chunks) - 1)
    )


def test_split_into_chunks_rejects_invalid_overlap():
    with pytest.raises(ValueError):
        split_into_chunks("some text", chunk_size=100, overlap=100)
