import hashlib
import io
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from botocore.exceptions import ClientError

from app.services.submission_storage import build_submission_storage_key, iter_original, original_content_disposition
from app.storage.base import StorageObjectExistsError, StorageUnavailableError
from app.storage.local import LocalStorageService
from app.storage.s3 import S3StorageService


def key():
    return build_submission_storage_key(*(uuid.uuid4() for _ in range(4)), hashlib.sha256(b"original").hexdigest())


def test_local_original_exclusive_create_and_round_trip(tmp_path):
    storage = LocalStorageService(str(tmp_path))
    original_key = key()
    data = b"byte-exact-original" * 100_000
    storage.save_new(original_key, io.BytesIO(data), "application/docx")
    with pytest.raises(StorageObjectExistsError):
        storage.save_new(original_key, io.BytesIO(b"replacement"), "application/docx")
    stream = storage.open(original_key)
    digest = hashlib.sha256()
    for chunk in iter_original(stream):
        assert len(chunk) <= 64 * 1024
        digest.update(chunk)
    assert digest.digest() == hashlib.sha256(data).digest()
    assert stream.closed


def test_local_concurrent_create_has_exactly_one_winner(tmp_path):
    storage = LocalStorageService(str(tmp_path))
    original_key = key()

    def create(index):
        try:
            storage.save_new(original_key, io.BytesIO(str(index).encode()), "application/docx")
            return index
        except StorageObjectExistsError:
            return None

    with ThreadPoolExecutor(max_workers=8) as executor:
        winners = [winner for winner in executor.map(create, range(16)) if winner is not None]
    assert len(winners) == 1
    assert storage.get(original_key) == str(winners[0]).encode()


def test_partial_local_failure_removes_only_new_object(tmp_path):
    storage = LocalStorageService(str(tmp_path))
    original_key = key()
    storage.save_new(original_key, io.BytesIO(b"keep"), "application/docx")
    failed_key = key()

    class BrokenStream:
        calls = 0

        def read(self, size):
            self.calls += 1
            if self.calls == 1:
                return b"partial"
            raise OSError("private internal details")

    with pytest.raises(StorageUnavailableError):
        storage.save_new(failed_key, BrokenStream(), "application/docx")
    assert not storage.exists(failed_key)
    assert storage.get(original_key) == b"keep"


def test_s3_conditional_put_is_private_and_never_overwrites():
    class FakeS3:
        objects = {}
        calls = []

        def put_object(self, **kwargs):
            self.calls.append(kwargs)
            assert kwargs["IfNoneMatch"] == "*"
            assert "ACL" not in kwargs
            if kwargs["Key"] in self.objects:
                raise ClientError({"Error": {"Code": "PreconditionFailed"}}, "PutObject")
            self.objects[kwargs["Key"]] = kwargs["Body"].read()

    client = FakeS3()
    storage = S3StorageService(client=client, bucket="private")
    original_key = key()
    storage.save_new(original_key, io.BytesIO(b"keep"), "application/docx")
    with pytest.raises(StorageObjectExistsError):
        storage.save_new(original_key, io.BytesIO(b"replace"), "application/docx")
    assert client.objects[original_key] == b"keep"


def test_download_disposition_cannot_inject_headers_or_paths():
    value = original_content_disposition("../../Отчёт\r\nX-Evil: yes.docx")
    assert value.startswith('attachment; filename="submission.docx"; filename*=UTF-8\'\'')
    assert "\r" not in value and "\n" not in value and "../" not in value
    assert "%D0" in value


def test_storage_key_rejects_user_input():
    with pytest.raises(ValueError):
        build_submission_storage_key("../tenant", uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), "a" * 64)
    with pytest.raises(ValueError):
        build_submission_storage_key(*(uuid.uuid4() for _ in range(4)), "../hash")


def test_s3_lost_put_acknowledgement_removes_only_the_current_object():
    class FailedPut:
        objects = {"existing": {"Metadata": {"pf-write-id": "older-write"}, "ETag": "old"}}

        def put_object(self, **kwargs):
            if kwargs["Key"] in self.objects:
                raise ClientError({"Error": {"Code": "PreconditionFailed"}}, "PutObject")
            self.objects[kwargs["Key"]] = {"Metadata": kwargs["Metadata"], "ETag": "new"}
            raise OSError("lost acknowledgement")

        def head_object(self, **kwargs):
            return self.objects[kwargs["Key"]]

        def delete_object(self, **kwargs):
            assert kwargs["IfMatch"] == self.objects[kwargs["Key"]]["ETag"]
            del self.objects[kwargs["Key"]]

    client = FailedPut()
    storage = S3StorageService(client=client, bucket="private")
    with pytest.raises(StorageUnavailableError):
        storage.save_new("new", io.BytesIO(b"new"), "application/docx")
    assert set(client.objects) == {"existing"}
    with pytest.raises(StorageObjectExistsError):
        storage.save_new("existing", io.BytesIO(b"replacement"), "application/docx")
    assert set(client.objects) == {"existing"}
