
# tests/test_ingestion.py

import pytest
from docx import Document as WordDocument

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
    from openpyxl import Workbook

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
