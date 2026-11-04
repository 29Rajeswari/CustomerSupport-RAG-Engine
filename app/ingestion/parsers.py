
from pathlib import Path

from docx import Document as WordDocument
from openpyxl import load_workbook
from pypdf import PdfReader


SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".txt"}


class DocumentParsingError(Exception):
    """Raised when a document cannot be extracted safely."""


def extract_text(file_path: str | Path) -> str:
    """Extract text from PDF, DOCX, XLSX or TXT files."""

    path = Path(file_path)

    if not path.exists() or not path.is_file():
        raise DocumentParsingError(f"File not found: {path}")

    extension = path.suffix.lower()

    if extension not in SUPPORTED_EXTENSIONS:
        raise DocumentParsingError(
            f"Unsupported file type: {extension}"
        )

    try:
        if extension == ".pdf":
            reader = PdfReader(str(path))

            if reader.is_encrypted:
                raise DocumentParsingError(
                    "Encrypted PDFs are not supported."
                )

            parts = []

            for page_number, page in enumerate(reader.pages, start=1):
                page_text = page.extract_text()

                if page_text:
                    parts.append(
                        f"[Page {page_number}]\n{page_text.strip()}"
                    )

            result = "\n\n".join(parts)

        elif extension == ".docx":
            document = WordDocument(str(path))
            parts = []

            for paragraph in document.paragraphs:
                if paragraph.text.strip():
                    parts.append(paragraph.text.strip())

            for table in document.tables:
                for row in table.rows:
                    cells = [
                        cell.text.strip().replace("\n", " ")
                        for cell in row.cells
                    ]

                    if any(cells):
                        parts.append(" | ".join(cells))

            result = "\n".join(parts)

        elif extension == ".xlsx":
            workbook = load_workbook(
                filename=path,
                read_only=True,
                data_only=True,
            )

            parts = []

            try:
                for worksheet in workbook.worksheets:
                    parts.append(f"[Worksheet: {worksheet.title}]")

                    for row in worksheet.iter_rows(values_only=True):
                        values = [
                            str(value).strip()
                            for value in row
                            if value is not None and str(value).strip()
                        ]

                        if values:
                            parts.append(" | ".join(values))
            finally:
                workbook.close()

            result = "\n".join(parts)

        else:
            result = _read_text_file(path)

    except DocumentParsingError:
        raise
    except Exception as exc:
        raise DocumentParsingError(
            f"Could not parse '{path.name}': {exc}"
        ) from exc

    result = result.replace("\x00", "").strip()

    if not result:
        raise DocumentParsingError(
            f"No readable text found in '{path.name}'."
        )

    return result


def _read_text_file(path: Path) -> str:
    """Read text using common Windows and Unicode encodings."""

    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue

    raise DocumentParsingError(
        "The text file encoding could not be recognized."
    )
