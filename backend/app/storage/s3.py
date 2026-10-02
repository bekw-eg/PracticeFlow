"""Private S3/MinIO implementation of :class:`StorageService`.

The adapter intentionally exposes neither object URLs nor presigned URLs.
Application routes perform their existing tenant/RBAC checks and then stream
bytes from this private bucket to the caller.
"""
from __future__ import annotations

import time
import uuid
from contextlib import suppress
from typing import BinaryIO, Iterator, cast

import boto3
from boto3.s3.transfer import TransferConfig
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings
from app.observability.metrics import metrics
from app.storage.base import StorageObjectExistsError, StorageService, StorageUnavailableError, validate_storage_key


_NOT_FOUND_CODES = {"404", "NoSuchKey", "NoSuchBucket", "NotFound"}
_STREAM_CHUNK_SIZE = 64 * 1024


class _S3ObjectStream:
    """Small iterator adapter accepted by Starlette's StreamingResponse."""

    def __init__(self, body):
        self._body = body
        self._closed = False

    def read(self, amount: int = -1) -> bytes:
        return self._body.read(amount)

    def __iter__(self) -> Iterator[bytes]:
        return self

    def __next__(self) -> bytes:
        chunk = self._body.read(_STREAM_CHUNK_SIZE)
        if chunk:
            return chunk
        self.close()
        raise StopIteration

    def close(self) -> None:
        if not self._closed:
            self._body.close()
            self._closed = True


class S3StorageService(StorageService):
    """A private, S3-compatible store shared by API and worker replicas."""

    def __init__(self, *, client=None, bucket: str | None = None):
        self.bucket = bucket or settings.S3_BUCKET
        if not self.bucket:
            raise ValueError("S3 bucket is required")
        self.client = client or boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL,
            region_name=settings.S3_REGION,
            aws_access_key_id=settings.S3_ACCESS_KEY_ID,
            aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY,
            verify=settings.S3_VERIFY_TLS,
            config=Config(signature_version="s3v4", s3={"addressing_style": settings.S3_ADDRESSING_STYLE}),
        )
        # Keep multipart uploads bounded and stream from the caller's staged
        # file. There is never a public ACL or public object URL in this path.
        self.transfer_config = TransferConfig(use_threads=False)

    @staticmethod
    def _is_not_found(exc: ClientError) -> bool:
        return str(exc.response.get("Error", {}).get("Code", "")) in _NOT_FOUND_CODES

    @staticmethod
    def _unavailable(exc: Exception) -> StorageUnavailableError:
        return StorageUnavailableError("Private object storage is unavailable")

    def save(self, key: str, data: BinaryIO, content_type: str) -> str:
        key = validate_storage_key(key)
        started = time.perf_counter()
        result = "failure"
        try:
            self.client.upload_fileobj(
                data,
                self.bucket,
                key,
                ExtraArgs={"ContentType": content_type},
                Config=self.transfer_config,
            )
        except (BotoCoreError, ClientError, OSError) as exc:
            raise self._unavailable(exc) from exc
        else:
            result = "success"
        finally:
            metrics.observe_storage_operation("s3", "upload", result, time.perf_counter() - started)
        return key

    def save_new(self, key: str, data: BinaryIO, content_type: str) -> str:
        key = validate_storage_key(key)
        started = time.perf_counter()
        result = "failure"
        write_id = uuid.uuid4().hex
        try:
            # A single conditional PUT accepts the bounded staged stream.
            # No preflight HEAD race, public ACL, or presigned URL is involved.
            self.client.put_object(
                Bucket=self.bucket, Key=key, Body=data, ContentType=content_type, IfNoneMatch="*",
                Metadata={"pf-write-id": write_id},
            )
            result = "success"
            return key
        except ClientError as exc:
            self._remove_failed_new_object(key, write_id)
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code in {"412", "PreconditionFailed", "ConditionalRequestConflict", "409"}:
                raise StorageObjectExistsError("Private object already exists") from exc
            raise self._unavailable(exc) from exc
        except (BotoCoreError, OSError) as exc:
            self._remove_failed_new_object(key, write_id)
            raise self._unavailable(exc) from exc
        finally:
            metrics.observe_storage_operation("s3", "upload", result, time.perf_counter() - started)

    def _remove_failed_new_object(self, key: str, write_id: str) -> None:
        # A remote PUT may succeed before its acknowledgement is lost. Only a
        # marker from this invocation authorizes removing that unowned object.
        # Never delete a pre-existing key after a conditional-write rejection.
        with suppress(BotoCoreError, ClientError, OSError, AttributeError):
            head = self.client.head_object(Bucket=self.bucket, Key=key)
            if head.get("Metadata", {}).get("pf-write-id") == write_id and head.get("ETag"):
                self.client.delete_object(Bucket=self.bucket, Key=key, IfMatch=head["ETag"])

    def get(self, key: str) -> bytes:
        key = validate_storage_key(key)
        started = time.perf_counter()
        metric_result = "failure"
        try:
            result = self.client.get_object(Bucket=self.bucket, Key=key)
            body = result["Body"]
            try:
                data = body.read()
                metric_result = "success"
                return data
            finally:
                body.close()
        except ClientError as exc:
            if self._is_not_found(exc):
                metric_result = "success"
                raise FileNotFoundError(key) from exc
            raise self._unavailable(exc) from exc
        except (BotoCoreError, OSError) as exc:
            raise self._unavailable(exc) from exc
        finally:
            metrics.observe_storage_operation("s3", "download", metric_result, time.perf_counter() - started)

    def open(self, key: str) -> BinaryIO:
        key = validate_storage_key(key)
        started = time.perf_counter()
        metric_result = "failure"
        try:
            result = self.client.get_object(Bucket=self.bucket, Key=key)
            stream = cast(BinaryIO, _S3ObjectStream(result["Body"]))
            metric_result = "success"
            return stream
        except ClientError as exc:
            if self._is_not_found(exc):
                metric_result = "success"
                raise FileNotFoundError(key) from exc
            raise self._unavailable(exc) from exc
        except (BotoCoreError, OSError) as exc:
            raise self._unavailable(exc) from exc
        finally:
            metrics.observe_storage_operation("s3", "download", metric_result, time.perf_counter() - started)

    def delete(self, key: str) -> None:
        key = validate_storage_key(key)
        started = time.perf_counter()
        result = "failure"
        try:
            # S3 delete is idempotent. No ACL is supplied, so the bucket and
            # its objects stay private under the deployment's bucket policy.
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except (BotoCoreError, ClientError, OSError) as exc:
            raise self._unavailable(exc) from exc
        else:
            result = "success"
        finally:
            metrics.observe_storage_operation("s3", "delete", result, time.perf_counter() - started)

    def exists(self, key: str) -> bool:
        key = validate_storage_key(key)
        started = time.perf_counter()
        metric_result = "failure"
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            metric_result = "success"
            return True
        except ClientError as exc:
            if self._is_not_found(exc):
                metric_result = "success"
                return False
            raise self._unavailable(exc) from exc
        except (BotoCoreError, OSError) as exc:
            raise self._unavailable(exc) from exc
        finally:
            metrics.observe_storage_operation("s3", "exists", metric_result, time.perf_counter() - started)

    def ping(self) -> bool:
        started = time.perf_counter()
        try:
            self.client.head_bucket(Bucket=self.bucket)
            available = True
        except (BotoCoreError, ClientError, OSError):
            available = False
        metrics.observe_storage_operation("s3", "ping", "success" if available else "failure", time.perf_counter() - started)
        metrics.observe_dependency("s3", "success" if available else "failure")
        return available
