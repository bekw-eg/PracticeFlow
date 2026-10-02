"""Preflight safety tests run without PostgreSQL or application fixtures."""
import hashlib
import io
import struct
import zipfile

import pytest
from fastapi import HTTPException, UploadFile
from pydantic import ValidationError

from app.core.config import Settings
from app.services.docx_preflight import DOCX_CONTENT_TYPE, normalize_original_filename, stage_docx_upload


CONTENT_TYPES = b'''<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'''
RELATIONSHIPS = b'''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>'''
DOCUMENT = b'''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Student original</w:t></w:r></w:p></w:body></w:document>'''


def make_docx(*, extra=None, omit=(), replacements=None, compression=zipfile.ZIP_DEFLATED):
    parts = {"[Content_Types].xml": CONTENT_TYPES, "_rels/.rels": RELATIONSHIPS, "word/document.xml": DOCUMENT}
    parts.update(replacements or {})
    parts.update(extra or {})
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=compression) as archive:
        for name, data in parts.items():
            if name not in omit:
                archive.writestr(name, data)
    return output.getvalue()


def upload(data, filename="original.docx"):
    return UploadFile(io.BytesIO(data), filename=filename)


def error_code(data, *, filename="original.docx", **limits):
    with pytest.raises(HTTPException) as caught:
        with stage_docx_upload(upload(data, filename), Settings(_env_file=None, **limits)):
            pytest.fail("Unsafe DOCX accepted")
    return caught.value.detail["code"]


def test_valid_docx_original_stays_byte_identical_with_bounded_reads_and_closed_tempfile():
    data = make_docx()

    class BoundedSource(io.BytesIO):
        def read(self, size=-1):
            assert 0 < size <= 64 * 1024
            return super().read(size)

    source = UploadFile(BoundedSource(data), filename="Student report.docx")
    with stage_docx_upload(source) as validated:
        assert validated.sha256 == hashlib.sha256(data).hexdigest()
        assert validated.size_bytes == len(data)
        assert validated.content_type == DOCX_CONTENT_TYPE
        assert validated.preflight_version == 1
        assert validated.stream.read() == data
        temporary = validated.stream
    assert temporary.closed


def test_real_python_docx_file_is_accepted():
    from docx import Document

    output = io.BytesIO()
    document = Document()
    document.add_paragraph("Исходный документ / Түпнұсқа құжат")
    document.save(output)
    with stage_docx_upload(upload(output.getvalue())) as validated:
        assert validated.sha256 == hashlib.sha256(output.getvalue()).hexdigest()


@pytest.mark.parametrize("filename", ["sample.doc", "sample.zip", "sample", "sample.docx.exe", ""])
def test_only_docx_filename_extension_is_allowed(filename):
    assert error_code(make_docx(), filename=filename) == "DOCX_EXTENSION"


def test_docm_extension_and_hidden_macro_payload_are_rejected():
    assert error_code(make_docx(), filename="sample.DOCM") == "DOCX_MACROS"
    assert error_code(make_docx(extra={"word/vbaProject.bin": b"macro"})) == "DOCX_MACROS"
    assert error_code(make_docx(extra={"word/VBAPROJECT.BIN": b"macro"})) == "DOCX_MACROS"
    macro_type = CONTENT_TYPES.replace(b"wordprocessingml.document.main+xml", b"word.macroEnabled.main+xml")
    assert error_code(make_docx(replacements={"[Content_Types].xml": macro_type})) == "DOCX_MACROS"


def test_ole_password_protected_office_signature_is_rejected():
    assert error_code(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"encrypted") == "DOCX_ENCRYPTED"


def test_encrypted_zip_flags_are_rejected():
    data = bytearray(make_docx())
    central_offset = data.index(b"PK\x01\x02")
    flags = struct.unpack_from("<H", data, central_offset + 8)[0]
    struct.pack_into("<H", data, central_offset + 8, flags | 1)
    assert error_code(bytes(data)) == "DOCX_ENCRYPTED"


def test_encrypted_local_flags_cannot_be_hidden_in_central_directory():
    data = bytearray(make_docx())
    flags = struct.unpack_from("<H", data, 6)[0]
    struct.pack_into("<H", data, 6, flags | 1)
    assert error_code(bytes(data)) == "DOCX_ENCRYPTED"


@pytest.mark.parametrize("name", ["../escape", "word/../escape", "/absolute", "C:/absolute", "word\\escape", "word/%2e%2e/escape", "word//escape"])
def test_unsafe_archive_paths_are_rejected(name):
    # Windows' ZIP writer normalises backslashes on creation. Mutate both
    # headers afterwards so this fixture contains the actual unsafe bytes.
    data = make_docx(extra={name: b"bad"})
    if "\\" in name:
        data = data.replace(name.replace("\\", "/").encode(), name.encode())
    assert error_code(data) == "DOCX_UNSAFE_ARCHIVE"


def test_symlink_zip_entry_is_rejected():
    output = io.BytesIO(make_docx())
    with zipfile.ZipFile(output, "a") as archive:
        entry = zipfile.ZipInfo("word/link")
        entry.create_system = 3
        entry.external_attr = 0o120777 << 16
        archive.writestr(entry, b"/etc/passwd")
    assert error_code(output.getvalue()) == "DOCX_UNSAFE_ARCHIVE"


def test_zip_bomb_ratio_and_entry_count_and_size_limits():
    assert error_code(make_docx(extra={"word/bomb.bin": b"A" * 200_000})) == "DOCX_COMPRESSION_RATIO"
    assert error_code(make_docx(), DOCX_MAX_ZIP_ENTRIES=2) == "DOCX_TOO_MANY_ENTRIES"
    assert error_code(make_docx(), DOCX_MAX_ENTRY_BYTES=20) == "DOCX_ARCHIVE_LIMIT"
    assert error_code(make_docx(), DOCX_MAX_UNCOMPRESSED_BYTES=100) == "DOCX_ARCHIVE_LIMIT"
    assert error_code(make_docx(), DOCX_MAX_UPLOAD_BYTES=100) == "DOCX_UPLOAD_TOO_LARGE"


@pytest.mark.parametrize("part", ["[Content_Types].xml", "_rels/.rels", "word/document.xml"])
def test_missing_required_parts_are_rejected(part):
    assert error_code(make_docx(omit=(part,))) == "DOCX_INVALID"


@pytest.mark.parametrize("data", [b"", b"not a zip", b"PK\x03\x04broken"])
def test_invalid_corrupt_and_empty_files_are_rejected(data):
    assert error_code(data) == "DOCX_INVALID"


def test_crc_damage_and_truncated_archive_are_rejected():
    data = make_docx(compression=zipfile.ZIP_STORED)
    damaged = data.replace(b"Student original", b"Student modified")
    assert error_code(damaged) == "DOCX_INVALID"
    assert error_code(data[:-30]) == "DOCX_INVALID"


def test_xml_doctype_external_entities_and_wrong_ooxml_are_rejected():
    malicious = b'''<!DOCTYPE document [<!ENTITY stolen SYSTEM "file:///etc/passwd">]><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>&stolen;</w:body></w:document>'''
    assert error_code(make_docx(replacements={"word/document.xml": malicious})) == "DOCX_INVALID"
    assert error_code(make_docx(replacements={"word/document.xml": b"<not-word/>"})) == "DOCX_INVALID"
    assert error_code(make_docx(replacements={"_rels/.rels": b"<Relationships/>"})) == "DOCX_INVALID"
    assert error_code(make_docx(extra={"word/styles.xml": b"<broken>"})) == "DOCX_INVALID"


def test_filename_is_normalized_without_header_path_or_bidi_injection():
    normalized = normalize_original_filename("C:\\fake\\../report\r\n\";x=1\u202e.docx")
    assert normalized.endswith(".docx")
    assert all(value not in normalized for value in ("/", "\\", "\r", "\n", '"', ";", "\u202e"))
    assert len(normalize_original_filename("a" * 500 + ".docx")) <= 180


@pytest.mark.parametrize("field", ["DOCX_MAX_UPLOAD_BYTES", "DOCX_MAX_ZIP_ENTRIES", "DOCX_MAX_UNCOMPRESSED_BYTES", "DOCX_MAX_ENTRY_BYTES", "DOCX_MAX_COMPRESSION_RATIO"])
def test_docx_limits_must_be_positive(field):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: 0})
