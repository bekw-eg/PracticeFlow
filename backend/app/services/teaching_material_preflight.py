"""Bounded file identification only: no rendering, analysis, or extraction."""
import hashlib
import re
import unicodedata
from contextlib import contextmanager
from dataclasses import dataclass
from tempfile import TemporaryFile
from typing import BinaryIO, Iterator
from urllib.parse import quote

from fastapi import HTTPException, UploadFile

from app.core.config import settings
from app.services.docx_preflight import CHUNK_BYTES, validate_office_package

MAX_MATERIAL_BYTES = 20 * 1024 * 1024
MATERIAL_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


def material_error(code: str, message: str, status: int = 400) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def material_filename(filename: str, extension: str) -> str:
    name = unicodedata.normalize("NFKC", filename).replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(char for char in name if not unicodedata.category(char).startswith("C"))
    name = re.sub(r'[<>:"/\\|?*%;]', "_", name).strip(" .")
    stem = name.rsplit(".", 1)[0][:175].strip(" .") or "material"
    return stem + "." + extension


def material_disposition(filename: str) -> str:
    return f"attachment; filename=\"material\"; filename*=UTF-8''{quote(filename, safe='')}"


@dataclass(frozen=True)
class ValidatedMaterial:
    stream: BinaryIO
    size_bytes: int
    sha256: str
    original_filename: str
    content_type: str
    extension: str


@contextmanager
def stage_material(upload: UploadFile) -> Iterator[ValidatedMaterial]:
    filename = (upload.filename or "").strip()
    extension = filename.rsplit(".", 1)[-1].lower()
    if extension not in MATERIAL_TYPES:
        raise material_error("MATERIAL_TYPE_UNSUPPORTED", "Upload a PDF, DOCX or PPTX file.")
    # Some browsers send a generic MIME. Bytes still determine acceptance.
    if upload.content_type not in {None, "", "application/octet-stream", MATERIAL_TYPES[extension]}:
        raise material_error("MATERIAL_TYPE_UNSUPPORTED", "The file type does not match its extension.")
    with TemporaryFile(mode="w+b") as staged:
        digest = hashlib.sha256()
        size = 0
        while chunk := upload.file.read(CHUNK_BYTES):
            size += len(chunk)
            if size > MAX_MATERIAL_BYTES:
                raise material_error("MATERIAL_TOO_LARGE", "The material exceeds the 20 MiB limit.", 413)
            digest.update(chunk)
            staged.write(chunk)
        if not size:
            raise material_error("MATERIAL_INVALID", "The material is empty or invalid.")
        staged.seek(0)
        if extension == "pdf":
            header = staged.read(16)
            staged.seek(max(0, size - 1024))
            if not re.match(rb"%PDF-(?:1\.[0-7]|2\.0)[\r\n ]", header) or not staged.read().rstrip().endswith(b"%%EOF"):
                raise material_error("MATERIAL_INVALID", "The file is not a PDF container.")
        else:
            try:
                validate_office_package(staged, settings, package_type=extension)
            except HTTPException as exc:
                raise material_error("MATERIAL_INVALID", "The Office file is invalid, encrypted, unsafe or contains macros.",
                                     exc.status_code) from None
        staged.seek(0)
        yield ValidatedMaterial(staged, size, digest.hexdigest(), material_filename(filename, extension),
                                MATERIAL_TYPES[extension], extension)
