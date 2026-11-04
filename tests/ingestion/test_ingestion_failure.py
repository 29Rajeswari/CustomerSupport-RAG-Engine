
from unittest.mock import MagicMock, patch

import pytest

from app.ingestion import processor


def test_embedding_failure_marks_version_failed(tmp_path):
    document_path = tmp_path / "new_warranty.txt"
    document_path.write_text(
        "Mixer grinder warranty covers manufacturing defects "
        "for twelve months.",
        encoding="utf-8",
    )

    document = MagicMock()
    document.id = 999001
    document.file_path = str(document_path)

    version = MagicMock()
    version.id = 999002
    version.document_id = 999001
    version.file_path = str(document_path)
    version.file_type = "txt"
    version.product_id = "MOB-1001"
    version.category = "warranty"
    version.is_active = False
    version.status = "processing"
    version.error_message = None

    initial_session = MagicMock()
    initial_session.__enter__.return_value = initial_session
    initial_session.__exit__.return_value = False

    failure_session = MagicMock()
    failure_session.__enter__.return_value = failure_session
    failure_session.__exit__.return_value = False
    failure_session.scalar.return_value = version

    # SessionLocal() is used for the initial document lookup.
    # SessionLocal.begin() is used to record the failed version.
    with (
        patch.object(
            processor,
            "SessionLocal",
        ) as session_factory,
        patch.object(
            processor,
            "_get_document_and_version",
            return_value=(document, version),
        ),
        patch.object(
            processor,
            "generate_embedding",
            side_effect=RuntimeError("Simulated embedding failure"),
        ),
    ):
        session_factory.return_value.__enter__.return_value = initial_session
        session_factory.return_value.__exit__.return_value = False

        session_factory.begin.return_value.__enter__.return_value = (
            failure_session
        )
        session_factory.begin.return_value.__exit__.return_value = False

        with pytest.raises(
            RuntimeError,
            match="Simulated embedding failure",
        ):
            processor.process_document_version(version.id)

    assert version.status == "failed"
    assert version.is_active is False
    assert "Simulated embedding failure" in version.error_message
    session_factory.begin.assert_called_once()


