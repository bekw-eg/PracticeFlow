"""Image upload for the document engine (rule 24/25). Uses the existing
StorageService abstraction from Phase 1 — this service never touches the
filesystem directly, so switching to S3/MinIO later doesn't change a line
here."""
import uuid
import warnings
from contextlib import suppress
from tempfile import TemporaryFile
from typing import BinaryIO, cast

from fastapi import HTTPException, UploadFile, status
from PIL import Image, UnidentifiedImageError

from app.core.config import settings
from app.models.enums import AuditEventType
from app.models.file import File
from app.repositories.file_repository import FileRepository
from app.resource_protection import ResourceGuard
from app.services.audit_service import AuditService
from app.storage import get_storage_service
from app.storage.base import StorageUnavailableError

UPLOAD_CHUNK_BYTES = 64 * 1024
MAX_IMAGE_PIXELS = 25_000_000
ALLOWED_CONTENT_TYPES = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}
PIL_FORMATS = {
    "PNG": ("image/png", "png"),
    "JPEG": ("image/jpeg", "jpg"),
    "WEBP": ("image/webp", "webp"),
}


class FileService:
    def __init__(self, db, resource_guard: ResourceGuard | None = None):
        self.db = db
        self.file_repo = FileRepository(db)
        self.audit = AuditService(db)
        self.storage = get_storage_service()
        self.resource_guard = resource_guard

    def upload_image(self, org_id: uuid.UUID, uploaded_by_user_id: uuid.UUID, upload: UploadFile) -> File:
        if upload.content_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported image type: {upload.content_type}. Allowed: PNG, JPEG, WEBP.",
            )

        if self.resource_guard is None:
            raise RuntimeError("A resource guard is required for uploads")

        # Multipart parsing may spool the request upstream, but this service
        # never builds an unbounded byte string. Once the configured maximum
        # is crossed, at most one 64KiB chunk has been read into memory.
        with TemporaryFile(mode="w+b") as staged:
            total_bytes = 0
            while chunk := upload.file.read(UPLOAD_CHUNK_BYTES):
                total_bytes += len(chunk)
                if total_bytes > settings.UPLOAD_MAX_FILE_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail="Image exceeds the configured file-size limit.",
                    )
                staged.write(chunk)
            if total_bytes == 0:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file.")

            try:
                staged.seek(0)
                with warnings.catch_warnings():
                    warnings.simplefilter("error", Image.DecompressionBombWarning)
                    with Image.open(staged) as image:
                        if image.width * image.height > MAX_IMAGE_PIXELS:
                            raise ValueError("Image dimensions are too large")
                        detected = PIL_FORMATS.get(image.format or "")
                        image.verify()
                    # verify() checks container integrity. Reopening and loading also
                    # exercises the decoder so truncated/corrupt pixel data is rejected.
                    staged.seek(0)
                    with Image.open(staged) as image:
                        image.load()
            except (Image.DecompressionBombError, Image.DecompressionBombWarning, UnidentifiedImageError, OSError, SyntaxError, ValueError):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or corrupt image file.") from None

            if detected is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported image encoding.")
            detected_content_type, extension = detected
            if upload.content_type != detected_content_type:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Declared content type does not match the {detected_content_type} file bytes.",
                )

            reservation = self.resource_guard.reserve_upload(
                org_id,
                uploaded_by_user_id,
                total_bytes,
                self.file_repo.total_size_bytes(org_id),
            )
            file_id = uuid.uuid4()
            storage_key = f"orgs/{org_id}/images/{file_id}.{extension}"
            file_saved = False
            try:
                staged.seek(0)
                self.storage.save(storage_key, cast(BinaryIO, staged), detected_content_type)
                file_saved = True
                file_row = File(
                    id=file_id,
                    organization_id=org_id,
                    uploaded_by_user_id=uploaded_by_user_id,
                    storage_key=storage_key,
                    original_filename=upload.filename or f"image.{extension}",
                    content_type=detected_content_type,
                    size_bytes=total_bytes,
                )
                self.file_repo.add(file_row)
                self.audit.record(
                    organization_id=org_id,
                    actor_user_id=uploaded_by_user_id,
                    event_type=AuditEventType.FILE_GENERATED,
                    entity_type="file",
                    entity_id=file_row.id,
                )
                self.db.commit()
                self.db.refresh(file_row)
            except StorageUnavailableError as exc:
                self.db.rollback()
                if file_saved:
                    with suppress(Exception):
                        self.storage.delete(storage_key)
                # Failure is closed conservatively: the user-period quota is
                # retained, while the organization reservation is released.
                self.resource_guard.cancel_upload(reservation)
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="File storage is temporarily unavailable. Please try again later.",
                ) from exc
            except Exception:
                self.db.rollback()
                if file_saved:
                    with suppress(Exception):
                        self.storage.delete(storage_key)
                # Failure is closed conservatively: the user-period quota is
                # retained, while the organization reservation is released.
                self.resource_guard.cancel_upload(reservation)
                raise

            # Failure to remove this short-lived Redis reservation after the
            # database commit is conservative (temporary extra quota usage),
            # so it must not turn a completed upload into a misleading error.
            with suppress(Exception):
                self.resource_guard.complete_upload(reservation)
            return file_row

    def get_bytes(self, org_id: uuid.UUID, file_id: uuid.UUID, actor_user_id: uuid.UUID | None = None) -> tuple[bytes, str]:
        file_row = self.file_repo.get(org_id, file_id)
        if file_row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
        try:
            data = self.storage.get(file_row.storage_key)
        except StorageUnavailableError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="File storage is temporarily unavailable. Please try again later.",
            ) from exc
        self.audit.record(
            organization_id=org_id,
            actor_user_id=actor_user_id,
            event_type=AuditEventType.FILE_DOWNLOADED,
            entity_type="file",
            entity_id=file_row.id,
            metadata={"size_bytes": file_row.size_bytes, "content_type": file_row.content_type.upper().replace("/", "_")},
        )
        self.db.commit()
        return data, file_row.content_type
