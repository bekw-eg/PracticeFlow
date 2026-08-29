from functools import lru_cache

from app.storage.base import StorageService
from app.storage.local import LocalStorageService
from app.storage.s3 import S3StorageService
from app.core.config import settings


@lru_cache
def get_storage_service() -> StorageService:
    if settings.STORAGE_BACKEND == "s3":
        return S3StorageService()
    return LocalStorageService()
