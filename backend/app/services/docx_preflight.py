"""Bounded OOXML security preflight; never edits or extracts a student original."""
from __future__ import annotations

import hashlib
import io
import re
import stat
import struct
import unicodedata
import zipfile
import zlib
from contextlib import contextmanager
from dataclasses import dataclass
from tempfile import TemporaryFile
from typing import BinaryIO, Iterator
from urllib.parse import unquote

from fastapi import HTTPException, UploadFile
from lxml import etree

from app.core.config import Settings, settings


DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PREFLIGHT_SCHEMA_VERSION = 1
CHUNK_BYTES = 64 * 1024
_CONTENT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
_RELS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_WORD_NAMESPACES = {
    "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "http://purl.oclc.org/ooxml/wordprocessingml/main",
}
_DOCUMENT_RELATIONSHIPS = {
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument",
    "http://purl.oclc.org/ooxml/officeDocument/relationships/officeDocument",
}
_MAIN_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
_OLE_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


@dataclass(frozen=True)
class ValidatedDocx:
    stream: BinaryIO
    size_bytes: int
    sha256: str
    original_filename: str
    content_type: str = DOCX_CONTENT_TYPE
    classification: str = "DOCX"
    preflight_version: int = PREFLIGHT_SCHEMA_VERSION


def _reject(code: str, message: str, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def normalize_original_filename(filename: str | None) -> str:
    """Keep a bounded human-readable basename without path/header controls."""
    name = unicodedata.normalize("NFKC", filename or "submission.docx")
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(char for char in name if not unicodedata.category(char).startswith("C"))
    name = re.sub(r'[<>:"/\\|?*%;]', "_", name).strip(" .")
    stem = name[:-5] if name.lower().endswith(".docx") else name
    stem = stem[:175].strip(" .") or "submission"
    if stem.upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        stem = "_" + stem
    return stem + ".docx"


def _safe_member_name(info: zipfile.ZipInfo) -> str:
    name = info.orig_filename
    # Normalise URI escapes only for validation, never for archive lookup.
    checked = unquote(name)
    components = checked.rstrip("/").split("/")
    if (
        not name or name != info.filename or checked.startswith(("/", "\\"))
        or "\\" in checked or ":" in checked
        or any(unicodedata.category(char).startswith("C") for char in checked)
        or any(part in {"", ".", ".."} for part in components)
        or stat.S_ISLNK(info.external_attr >> 16)
    ):
        raise _reject("DOCX_UNSAFE_ARCHIVE", "The document contains unsafe archive paths.")
    return name


def _parse_xml(data: bytes) -> etree._Element:
    # Do not load DTDs, resolve entities, access the network, or enable the
    # parser's huge-tree escape hatch. Reject DTD declarations entirely.
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False)
    try:
        tree = etree.parse(io.BytesIO(data), parser)
        if tree.docinfo.doctype:
            raise _reject("DOCX_INVALID", "The document contains unsupported XML declarations.")
        return tree.getroot()
    except etree.XMLSyntaxError:
        raise _reject("DOCX_INVALID", "The DOCX file is invalid or corrupt.") from None


def validate_office_package(stream: BinaryIO, limits: Settings, *, package_type: str = "docx") -> None:
    # Teaching materials reuse these bounded ZIP/XML checks for PPTX. The
    # default retains the original DOCX acceptance policy without analysis.
    presentation = package_type == "pptx"
    main_part = "ppt/presentation.xml" if presentation else "word/document.xml"
    main_type = ("application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"
                 if presentation else _MAIN_TYPE)
    namespaces = {"http://schemas.openxmlformats.org/presentationml/2006/main",
                  "http://purl.oclc.org/ooxml/presentationml/main"} if presentation else _WORD_NAMESPACES
    root_name = "presentation" if presentation else "document"
    required_parts = {"[Content_Types].xml", "_rels/.rels", main_part}
    stream.seek(0)
    signature = stream.read(8)
    if signature == _OLE_SIGNATURE:
        raise _reject("DOCX_ENCRYPTED", "Encrypted or legacy Office files are not supported. Upload an unencrypted DOCX.")
    if not signature.startswith(b"PK\x03\x04"):
        raise _reject("DOCX_INVALID", "The file is not a valid DOCX document.")
    stream.seek(0)
    try:
        with zipfile.ZipFile(stream) as archive:
            entries = archive.infolist()
            if len(entries) > limits.DOCX_MAX_ZIP_ENTRIES:
                raise _reject("DOCX_TOO_MANY_ENTRIES", "The document contains too many archive entries.")
            names: set[str] = set()
            total_declared = 0
            for info in entries:
                name = _safe_member_name(info)
                if name in names:
                    raise _reject("DOCX_INVALID", "The DOCX file contains duplicate archive entries.")
                names.add(name)
                if info.flag_bits & 0x1 or info.flag_bits & 0x40:
                    raise _reject("DOCX_ENCRYPTED", "Encrypted DOCX files are not supported.")
                # Inspect local flags too: a hostile central directory can
                # hide the encryption flag from ZIP readers using its values.
                stream.seek(info.header_offset)
                local_header = stream.read(30)
                if len(local_header) != 30 or local_header[:4] != b"PK\x03\x04":
                    raise _reject("DOCX_INVALID", "The DOCX file is invalid or corrupt.")
                local_flags = struct.unpack_from("<H", local_header, 6)[0]
                if local_flags & 0x1 or local_flags & 0x40:
                    raise _reject("DOCX_ENCRYPTED", "Encrypted DOCX files are not supported.")
                if "vbaproject" in unquote(name).lower() or "vbadata" in unquote(name).lower():
                    raise _reject("DOCX_MACROS", "Documents containing macros are not supported. Upload a macro-free DOCX.")
                if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                    raise _reject("DOCX_INVALID", "The DOCX uses an unsupported archive encoding.")
                total_declared += info.file_size
                if info.file_size > limits.DOCX_MAX_ENTRY_BYTES or total_declared > limits.DOCX_MAX_UNCOMPRESSED_BYTES:
                    raise _reject("DOCX_ARCHIVE_LIMIT", "The unpacked document exceeds the safety limit.", 413)
                if info.file_size / max(1, info.compress_size) > limits.DOCX_MAX_COMPRESSION_RATIO:
                    raise _reject("DOCX_COMPRESSION_RATIO", "The document compression exceeds the safety limit.", 413)
            if not required_parts.issubset(names):
                raise _reject("DOCX_INVALID", "The file is missing required DOCX parts.")

            parsed: dict[str, etree._Element] = {}
            total_actual = 0
            for info in entries:
                if info.is_dir():
                    continue
                xml_data = bytearray() if info.filename.lower().endswith((".xml", ".rels")) else None
                actual = 0
                with archive.open(info) as member:
                    # Reading every entry verifies decompression, CRC, local
                    # headers and actual size, not just central-directory claims.
                    while chunk := member.read(CHUNK_BYTES):
                        actual += len(chunk)
                        total_actual += len(chunk)
                        if actual > limits.DOCX_MAX_ENTRY_BYTES or total_actual > limits.DOCX_MAX_UNCOMPRESSED_BYTES:
                            raise _reject("DOCX_ARCHIVE_LIMIT", "The unpacked document exceeds the safety limit.", 413)
                        if actual / max(1, info.compress_size) > limits.DOCX_MAX_COMPRESSION_RATIO:
                            raise _reject("DOCX_COMPRESSION_RATIO", "The document compression exceeds the safety limit.", 413)
                        if xml_data is not None:
                            xml_data.extend(chunk)
                if actual != info.file_size:
                    raise _reject("DOCX_INVALID", "The DOCX file is invalid or corrupt.")
                if xml_data is not None:
                    root = _parse_xml(bytes(xml_data))
                    if info.filename in required_parts:
                        parsed[info.filename] = root

            content = parsed["[Content_Types].xml"]
            if content.tag != f"{{{_CONTENT_NS}}}Types":
                raise _reject("DOCX_INVALID", "The DOCX content types are invalid.")
            main_parts = []
            for node in content:
                declared_type = node.get("ContentType", "").lower()
                if "macroenabled" in declared_type or "vbaproject" in declared_type or "vbadata" in declared_type:
                    raise _reject("DOCX_MACROS", "Documents containing macros are not supported. Upload a macro-free DOCX.")
                if node.tag == f"{{{_CONTENT_NS}}}Override" and node.get("PartName") == "/" + main_part:
                    main_parts.append(declared_type)
            if main_parts != [main_type]:
                raise _reject("DOCX_INVALID", "The file does not contain a DOCX main document.")
            relationships = parsed["_rels/.rels"]
            if relationships.tag != f"{{{_RELS_NS}}}Relationships":
                raise _reject("DOCX_INVALID", "The DOCX relationships are invalid.")
            main_relationships = [node for node in relationships if node.get("Type") in _DOCUMENT_RELATIONSHIPS]
            if len(main_relationships) != 1 or (
                main_relationships[0].get("Target") not in {main_part, "/" + main_part}
                or main_relationships[0].get("TargetMode", "Internal") != "Internal"
            ):
                raise _reject("DOCX_INVALID", "The DOCX main document relationship is invalid.")
            if parsed[main_part].tag not in {f"{{{ns}}}{root_name}" for ns in namespaces}:
                raise _reject("DOCX_INVALID", "The DOCX main document XML is invalid.")
    except (zipfile.BadZipFile, zipfile.LargeZipFile, zlib.error, EOFError, NotImplementedError, KeyError, ValueError):
        raise _reject("DOCX_INVALID", "The DOCX file is invalid or corrupt.") from None
    except RuntimeError:
        raise _reject("DOCX_ENCRYPTED", "Encrypted DOCX files are not supported.") from None
    finally:
        stream.seek(0)


@contextmanager
def stage_docx_upload(upload: UploadFile, limits: Settings | None = None) -> Iterator[ValidatedDocx]:
    limits = limits or settings
    filename = (upload.filename or "").strip()
    if filename.lower().endswith(".docm"):
        raise _reject("DOCX_MACROS", "Macro-enabled files are not supported. Upload a macro-free DOCX.")
    if not filename.lower().endswith(".docx"):
        raise _reject("DOCX_EXTENSION", "Only .docx files are supported.")
    with TemporaryFile(mode="w+b") as staged:
        digest = hashlib.sha256()
        size = 0
        while chunk := upload.file.read(CHUNK_BYTES):
            size += len(chunk)
            if size > limits.DOCX_MAX_UPLOAD_BYTES:
                raise _reject("DOCX_UPLOAD_TOO_LARGE", "The DOCX exceeds the upload size limit.", 413)
            staged.write(chunk)
            digest.update(chunk)
        if not size:
            raise _reject("DOCX_INVALID", "The DOCX file is empty.")
        validate_office_package(staged, limits)
        yield ValidatedDocx(
            stream=staged, size_bytes=size, sha256=digest.hexdigest(),
            original_filename=normalize_original_filename(filename),
        )
