"""Runs only inside docker-compose.e2e.yml against its disposable MinIO."""
import io
import hashlib
import os
import uuid

import pytest

from app.storage import get_storage_service
from app.storage.base import StorageObjectExistsError
from app.services.submission_storage import build_submission_storage_key, iter_original


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


def test_minio_original_conditional_creation_and_byte_exact_download():
    storage = get_storage_service()
    payload = b"private-original-byte-exact" * 10_000
    checksum = hashlib.sha256(payload).hexdigest()
    key = build_submission_storage_key(*(uuid.uuid4() for _ in range(4)), checksum)
    created = False
    try:
        storage.save_new(key, io.BytesIO(payload), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        created = True
        with pytest.raises(StorageObjectExistsError):
            storage.save_new(key, io.BytesIO(b"replacement"), "application/docx")
        downloaded = b"".join(iter_original(storage.open(key)))
        assert hashlib.sha256(downloaded).hexdigest() == checksum
        assert downloaded == payload
    finally:
        if created:
            storage.delete(key)
