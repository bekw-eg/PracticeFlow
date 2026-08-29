import os
import shutil
import time
from pathlib import Path
from typing import BinaryIO

from app.core.config import settings
from app.observability.metrics import metrics
from app.storage.base import StorageService, validate_storage_key


class LocalStorageService(StorageService):
    """Phase 1 storage backend: plain local filesystem, rooted at
    settings.STORAGE_LOCAL_PATH. `key` is a relative path under that root —
    callers never see or construct an absolute path."""

    def __init__(self, root: str | None = None):
        self.root = Path(root or settings.STORAGE_LOCAL_PATH)
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        # Prevent path traversal outside the storage root via a crafted key.
        validate_storage_key(key)
        resolved = (self.root / key).resolve()
        if self.root.resolve() not in resolved.parents and resolved != self.root.resolve():
            raise ValueError("Invalid storage key")
        return resolved

    def save(self, key: str, data: BinaryIO, content_type: str) -> str:
        started = time.perf_counter()
        result = "failure"
        path = self._resolve(key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "wb") as f:
                # Copy incrementally: callers may pass a staged multipart upload,
                # which must not be read back into process memory in one call.
                shutil.copyfileobj(data, f, length=64 * 1024)
            result = "success"
        finally:
            metrics.observe_storage_operation("local", "upload", result, time.perf_counter() - started)
        return key

    def get(self, key: str) -> bytes:
        started = time.perf_counter()
        result = "failure"
        try:
            with open(self._resolve(key), "rb") as f:
                data = f.read()
            result = "success"
            return data
        finally:
            metrics.observe_storage_operation("local", "download", result, time.perf_counter() - started)

    def open(self, key: str) -> BinaryIO:
        started = time.perf_counter()
        result = "failure"
        try:
            stream = open(self._resolve(key), "rb")
            result = "success"
            return stream
        finally:
            metrics.observe_storage_operation("local", "download", result, time.perf_counter() - started)

    def delete(self, key: str) -> None:
        started = time.perf_counter()
        result = "failure"
        try:
            path = self._resolve(key)
            if path.exists():
                os.remove(path)
            result = "success"
        finally:
            metrics.observe_storage_operation("local", "delete", result, time.perf_counter() - started)

    def exists(self, key: str) -> bool:
        started = time.perf_counter()
        result = "failure"
        try:
            exists = self._resolve(key).exists()
            result = "success"
            return exists
        finally:
            metrics.observe_storage_operation("local", "exists", result, time.perf_counter() - started)

    def ping(self) -> bool:
        started = time.perf_counter()
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            available = self.root.is_dir()
        except OSError:
            available = False
        metrics.observe_storage_operation("local", "ping", "success" if available else "failure", time.perf_counter() - started)
        metrics.observe_dependency("local_storage", "success" if available else "failure")
        return available
