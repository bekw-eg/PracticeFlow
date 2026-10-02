"""StorageService abstraction (rule 18/36).

Domain/service code depends on this interface only — never on the
filesystem, boto3, or any concrete backend directly. That's what lets the
storage backend move from local disk (Phase 1) to S3/MinIO/Azure Blob later
without touching a single service or route handler.
"""
from abc import ABC, abstractmethod
from typing import BinaryIO


class StorageUnavailableError(RuntimeError):
    """The configured private object store cannot complete an operation."""


class StorageObjectExistsError(StorageUnavailableError):
    """Exclusive creation failed; the pre-existing object must not be deleted."""


def validate_storage_key(key: str) -> str:
    """Defence in depth for storage-key callers and every backend.

    Domain services generate these keys from UUIDs.  This guard makes that
    invariant explicit and rejects path-like input before it reaches local
    disk or an object-store namespace.
    """

    if not isinstance(key, str) or not key or key.startswith("/") or "\\" in key or "\x00" in key:
        raise ValueError("Invalid storage key")
    parts = key.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("Invalid storage key")
    return key


class StorageService(ABC):
    def save_new(self, key: str, data: BinaryIO, content_type: str) -> str:
        """Create a private object atomically, refusing any existing key.

        Backends must implement real exclusive creation; an exists/save pair
        is unsafe under concurrent requests. Unknown adapters fail closed.
        """
        raise StorageUnavailableError("Exclusive object creation is unavailable")

    @abstractmethod
    def save(self, key: str, data: BinaryIO, content_type: str) -> str:
        """Persists data under `key`, returns the storage key actually used."""
        ...

    @abstractmethod
    def get(self, key: str) -> bytes:
        ...

    @abstractmethod
    def open(self, key: str) -> BinaryIO:
        """Open an artifact for streaming. Callers close the returned handle."""
        ...

    @abstractmethod
    def delete(self, key: str) -> None:
        ...

    @abstractmethod
    def exists(self, key: str) -> bool:
        ...

    @abstractmethod
    def ping(self) -> bool:
        """Return whether this backend can currently serve private objects."""
        ...
