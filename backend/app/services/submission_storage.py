"""Private original storage helpers; ownership checks belong to the domain service."""
from __future__ import annotations

import re
import uuid
from typing import BinaryIO, Iterator
from urllib.parse import quote

from app.services.docx_preflight import CHUNK_BYTES, ValidatedDocx, normalize_original_filename
from app.storage.base import StorageService


def build_submission_storage_key(
    organization_id: uuid.UUID, assignment_id: uuid.UUID, student_id: uuid.UUID,
    submission_id: uuid.UUID, sha256: str,
) -> str:
    if not all(isinstance(value, uuid.UUID) for value in (organization_id, assignment_id, student_id, submission_id)):
        raise ValueError("Submission storage identifiers must be UUIDs")
    if not re.fullmatch(r"[0-9a-f]{64}", sha256):
        raise ValueError("Invalid SHA-256")
    return (
        f"orgs/{organization_id}/document-checks/{assignment_id}/students/{student_id}/"
        f"submissions/{submission_id}/{sha256}.docx"
    )


def build_teacher_submission_storage_key(
    organization_id: uuid.UUID,
    teacher_id: uuid.UUID,
    submission_id: uuid.UUID,
    sha256: str,
) -> str:
    if not all(isinstance(value, uuid.UUID) for value in (organization_id, teacher_id, submission_id)):
        raise ValueError("Teacher submission storage identifiers must be UUIDs")
    if not re.fullmatch(r"[0-9a-f]{64}", sha256):
        raise ValueError("Invalid SHA-256")
    return (
        f"orgs/{organization_id}/document-checks/teachers/{teacher_id}/"
        f"submissions/{submission_id}/{sha256}.docx"
    )


def persist_original(storage: StorageService, key: str, validated: ValidatedDocx) -> str:
    validated.stream.seek(0)
    return storage.save_new(key, validated.stream, validated.content_type)


def iter_original(stream: BinaryIO) -> Iterator[bytes]:
    try:
        while chunk := stream.read(CHUNK_BYTES):
            yield chunk
    finally:
        stream.close()


def original_content_disposition(filename: str) -> str:
    safe_name = normalize_original_filename(filename)
    return f"attachment; filename=\"submission.docx\"; filename*=UTF-8''{quote(safe_name, safe='')}"
