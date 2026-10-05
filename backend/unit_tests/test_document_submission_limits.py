import asyncio
import json

from fastapi import FastAPI, UploadFile
import pytest

from app.core.config import settings
from app.document_submission_limits import DocumentSubmissionBodyLimitMiddleware


@pytest.mark.parametrize("path", [
    "/api/v1/document-checks/teacher/submissions",
    "/api/v1/document-checks/student/assignments/test/submissions",
    "/api/v1/topics/test/materials",
])
def test_chunked_upload_limit_closes_partial_spooled_files(monkeypatch, path):
    import starlette.formparsers as parsers

    monkeypatch.setattr(settings, "DOCX_MAX_UPLOAD_BYTES", 10)
    monkeypatch.setattr("app.document_submission_limits.MAX_MATERIAL_BYTES", 10)
    files = []
    original = parsers.SpooledTemporaryFile

    def track(*args, **kwargs):
        result = original(*args, **kwargs)
        files.append(result)
        return result

    monkeypatch.setattr(parsers, "SpooledTemporaryFile", track)
    app = FastAPI()
    app.add_middleware(DocumentSubmissionBodyLimitMiddleware)
    called = []

    @app.post("/api/v1/document-checks/student/assignments/test/submissions")
    def upload(file: UploadFile):
        called.append(file)
        return {"accepted": True}

    app.post("/api/v1/document-checks/teacher/submissions")(upload)
    app.post("/api/v1/topics/test/materials")(upload)

    header = b'--test\r\nContent-Disposition: form-data; name="file"; filename="test.docx"\r\n\r\n'
    chunks = iter([header + b"partial", b"X" * (64 * 1024), b"\r\n--test--\r\n"])
    messages = []

    async def receive():
        return {"type": "http.request", "body": next(chunks), "more_body": True}

    async def send(message):
        messages.append(message)

    asyncio.run(app({
        "type": "http", "http_version": "1.1", "method": "POST", "scheme": "http",
        "path": path, "query_string": b"",
        "headers": [(b"content-type", b"multipart/form-data; boundary=test")],
        "server": ("localhost", 80), "client": ("localhost", 1234),
    }, receive, send))
    assert messages[0]["status"] == 413
    assert json.loads(messages[1]["body"])["detail"]["code"] == (
        "MATERIAL_TOO_LARGE" if "/topics/" in path else "DOCX_UPLOAD_TOO_LARGE"
    )
    assert called == []
    assert files and all(file.closed for file in files)
