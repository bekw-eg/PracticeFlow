"""Runs only inside docker-compose.e2e.yml against its disposable MinIO."""
import io
import os
import uuid

import pytest

from app.storage import get_storage_service


pytestmark = pytest.mark.skipif(
    os.getenv("S3_MINIO_INTEGRATION") != "1",
    reason="requires the disposable private MinIO integration environment",
)


def test_minio_round_trip_and_cleanup_for_export_artifact():
    storage = get_storage_service()
    key = f"orgs/{uuid.uuid4()}/exports/{uuid.uuid4()}.docx"
    payload = b"private-export-artifact"

    storage.save(key, io.BytesIO(payload), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    assert storage.get(key) == payload
    stream = storage.open(key)
    try:
        assert b"".join(stream) == payload
    finally:
        stream.close()

    storage.delete(key)
    assert storage.exists(key) is False
