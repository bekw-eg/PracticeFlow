import io

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

from app.storage.base import StorageUnavailableError
from app.storage.s3 import S3StorageService


class _FakeS3Client:
    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.upload_calls: list[dict] = []
        self.available = True

    def _unavailable(self):
        if not self.available:
            raise EndpointConnectionError(endpoint_url="http://objects.invalid")

    def upload_fileobj(self, data, bucket, key, **kwargs):
        self._unavailable()
        self.upload_calls.append({"bucket": bucket, "key": key, **kwargs})
        self.objects[key] = data.read()

    def get_object(self, Bucket, Key):
        self._unavailable()
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        return {"Body": io.BytesIO(self.objects[Key])}

    def head_object(self, Bucket, Key):
        self._unavailable()
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        return {}

    def delete_object(self, Bucket, Key):
        self._unavailable()
        self.objects.pop(Key, None)

    def head_bucket(self, Bucket):
        self._unavailable()
        return {}


def _service(client: _FakeS3Client) -> S3StorageService:
    return S3StorageService(client=client, bucket="private-practiceflow")


def test_private_s3_adapter_streams_objects_without_acl_or_object_urls():
    client = _FakeS3Client()
    storage = _service(client)
    key = "orgs/11111111-1111-1111-1111-111111111111/images/22222222-2222-2222-2222-222222222222.png"

    assert storage.save(key, io.BytesIO(b"image-bytes"), "image/png") == key
    assert client.upload_calls[0]["ExtraArgs"] == {"ContentType": "image/png"}
    assert storage.get(key) == b"image-bytes"
    stream = storage.open(key)
    try:
        assert b"".join(stream) == b"image-bytes"
    finally:
        stream.close()
    assert storage.exists(key)
    storage.delete(key)
    assert not storage.exists(key)


@pytest.mark.parametrize("key", ["../escape", "/absolute", "orgs/../escape", "orgs\\escape", "orgs//escape"])
def test_s3_adapter_rejects_non_server_generated_path_like_keys(key):
    with pytest.raises(ValueError, match="Invalid storage key"):
        _service(_FakeS3Client()).save(key, io.BytesIO(b"x"), "image/png")


def test_s3_adapter_fails_closed_when_private_backend_is_unavailable():
    client = _FakeS3Client()
    client.available = False
    storage = _service(client)

    with pytest.raises(StorageUnavailableError):
        storage.save("orgs/a/images/b.png", io.BytesIO(b"x"), "image/png")
    assert storage.ping() is False
