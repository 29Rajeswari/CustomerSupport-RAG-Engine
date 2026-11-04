
from unittest.mock import MagicMock, patch

import pytest

from app.ingestion import processor


def test_embedding_failure_does_not_start_activation_transaction(
    tmp_path,
):
    document_path = tmp_path / "new_warranty.txt"
    document_path.write_text(
        "Mixer grinder warranty covers manufacturing defects "
        "for twelve months.",
        encoding="utf-8",
    )

    new_document = MagicMock()
    new_document.id = 999001
    new_document.file_path = str(document_path)

    new_version = MagicMock()
    new_version.id = 999002
    new_version.document_id = 999001
    new_version.is_active = False
    new_version.status = "processing"
    new_version.error_message = None

    initial_session = MagicMock()
    initial_session.__enter__.return_value = initial_session
    initial_session.__exit__.return_value = False

    failure_session = MagicMock()
    failure_session.__enter__.return_value = failure_session
    failure_session.__exit__.return_value = False

    with (
        patch.object(
            processor,
            "SessionLocal",
            side_effect=[initial_session, failure_session],
        ) as session_factory,
        patch.object(
            processor,
            "_get_document_and_version",
            return_value=(new_document, new_version),
        ),
        patch.object(
            processor,
            "generate_embedding",
            side_effect=RuntimeError("Simulated embedding failure"),
        ),
    ):
        # Return the actual version object in both sessions.
        initial_session.scalar.return_value = new_version
        failure_session.scalar.return_value = new_version

        with pytest.raises(
            RuntimeError,
            match="Simulated embedding failure",
        ):
            processor.process_document_version(999002)

    assert new_version.status == "failed"
    assert new_version.is_active is False
    assert "Simulated embedding failure" in new_version.error_message

    # Initial lookup and failure handler only; activation was never entered.
    assert session_factory.call_count == 2
