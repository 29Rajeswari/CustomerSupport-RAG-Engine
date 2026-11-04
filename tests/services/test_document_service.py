
from pathlib import Path

import pytest

from app.services.document_service import (
    ALLOWED_EXTENSIONS,
    get_upload_directory,
    validate_document_file,
)


@pytest.mark.parametrize(
    "filename, expected",
    [
        ("warranty.pdf", ".pdf"),
        ("product-manual.docx", ".docx"),
        ("catalog.xlsx", ".xlsx"),
        ("faq.txt", ".txt"),
        ("WARRANTY.PDF", ".pdf"),
    ],
)
def test_validate_document_file_accepts_supported_extensions(
    filename, expected
):
    assert validate_document_file(filename) == expected


@pytest.mark.parametrize(
    "filename",
    [
        "script.exe",
        "document.csv",
        "image.png",
        "no_extension",
    ],
)
def test_validate_document_file_rejects_unsupported_extensions(filename):
    with pytest.raises(ValueError, match="Unsupported file type"):
        validate_document_file(filename)


def test_allowed_extensions_are_expected():
    assert ALLOWED_EXTENSIONS == {".pdf", ".docx", ".xlsx", ".txt"}


def test_get_upload_directory_creates_configured_directory(
    tmp_path, monkeypatch
):
    from app.services import document_service

    test_directory = tmp_path / "test_uploads"

    monkeypatch.setattr(
        document_service.settings,
        "UPLOAD_DIR",
        str(test_directory),
    )
    monkeypatch.setattr(
        document_service,
        "PROJECT_ROOT",
        tmp_path,
    )

    result = get_upload_directory()

    assert result == test_directory
    assert result.exists()
    assert result.is_dir()

def test_save_uploaded_file_creates_unique_file(tmp_path, monkeypatch):
    from app.services import document_service

    monkeypatch.setattr(
        document_service,
        "get_upload_directory",
        lambda: tmp_path,
    )

    first = document_service.save_uploaded_file(
        "manual.pdf",
        b"sample PDF content",
    )
    second = document_service.save_uploaded_file(
        "manual.pdf",
        b"different PDF content",
    )

    assert first.exists()
    assert second.exists()
    assert first != second
    assert first.read_bytes() == b"sample PDF content"
    assert second.read_bytes() == b"different PDF content"
    assert first.parent == tmp_path


def test_save_uploaded_file_rejects_empty_content(tmp_path, monkeypatch):
    from app.services import document_service

    monkeypatch.setattr(
        document_service,
        "get_upload_directory",
        lambda: tmp_path,
    )

    with pytest.raises(ValueError, match="empty"):
        document_service.save_uploaded_file("manual.pdf", b"")


def test_save_uploaded_file_rejects_unsupported_extension(tmp_path, monkeypatch):
    from app.services import document_service

    monkeypatch.setattr(
        document_service,
        "get_upload_directory",
        lambda: tmp_path,
    )

    with pytest.raises(ValueError, match="Unsupported file type"):
        document_service.save_uploaded_file("program.exe", b"content")


def test_save_uploaded_file_rejects_file_over_size_limit(
    tmp_path, monkeypatch
):
    from app.services import document_service

    monkeypatch.setattr(
        document_service,
        "get_upload_directory",
        lambda: tmp_path,
    )
    monkeypatch.setattr(
        document_service.settings,
        "MAX_UPLOAD_SIZE_MB",
        1,
    )

    content = b"x" * (1024 * 1024 + 1)

    with pytest.raises(ValueError, match="maximum size"):
        document_service.save_uploaded_file("large.txt", content)


def test_save_uploaded_file_requires_bytes():
    from app.services.document_service import save_uploaded_file

    with pytest.raises(TypeError, match="must be bytes"):
        save_uploaded_file("manual.txt", "not bytes")

