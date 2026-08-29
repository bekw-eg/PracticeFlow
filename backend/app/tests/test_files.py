import io

from PIL import Image

from app.storage.base import StorageUnavailableError
from app.tests.conftest import OrgFixture, auth_headers


def _png_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGBA", (1, 1), (0, 0, 0, 0)).save(output, format="PNG")
    return output.getvalue()


def test_upload_valid_png_succeeds(client, org_a: OrgFixture):
    token = org_a.teacher_token(client)
    resp = client.post(
        "/api/v1/files",
        headers=auth_headers(token),
        files={"file": ("test.png", io.BytesIO(_png_bytes()), "image/png")},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["content_type"] == "image/png"
    assert "/api/v1/files/" in body["url"]


def test_upload_rejects_disallowed_mime_type(client, org_a: OrgFixture):
    token = org_a.teacher_token(client)
    resp = client.post(
        "/api/v1/files",
        headers=auth_headers(token),
        files={"file": ("script.js", io.BytesIO(b"alert(1)"), "application/javascript")},
    )
    assert resp.status_code == 400


def test_upload_rejects_oversized_file(client, org_a: OrgFixture):
    token = org_a.teacher_token(client)
    oversized = b"\x00" * (5 * 1024 * 1024 + 1)
    resp = client.post(
        "/api/v1/files",
        headers=auth_headers(token),
        files={"file": ("big.png", io.BytesIO(oversized), "image/png")},
    )
    assert resp.status_code == 413


def test_upload_rejects_malformed_image_with_allowed_mime(client, org_a: OrgFixture):
    token = org_a.teacher_token(client)
    resp = client.post(
        "/api/v1/files",
        headers=auth_headers(token),
        files={"file": ("fake.png", io.BytesIO(b"not really a png"), "image/png")},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid or corrupt image file."


def test_upload_rejects_crc_broken_png_as_a_validation_error(client, org_a: OrgFixture):
    token = org_a.teacher_token(client)
    # Parsed as PNG by Pillow but rejected during `verify()` with SyntaxError.
    crc_broken_png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\xdac`\xf8\xcf\xf0\x1f\x00\x05\xfe\x02\xfe\x31\xb6\xc0\xf3\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    response = client.post(
        "/api/v1/files",
        headers=auth_headers(token),
        files={"file": ("broken.png", io.BytesIO(crc_broken_png), "image/png")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid or corrupt image file."


def test_upload_rejects_content_type_mismatch(client, org_a: OrgFixture):
    token = org_a.teacher_token(client)
    resp = client.post(
        "/api/v1/files",
        headers=auth_headers(token),
        files={"file": ("fake.jpg", io.BytesIO(_png_bytes()), "image/jpeg")},
    )
    assert resp.status_code == 400
    assert "does not match" in resp.json()["detail"]


def test_uploaded_file_can_be_retrieved_by_uploader(client, org_a: OrgFixture):
    token = org_a.teacher_token(client)
    upload_resp = client.post(
        "/api/v1/files",
        headers=auth_headers(token),
        files={"file": ("test.png", io.BytesIO(_png_bytes()), "image/png")},
    )
    file_id = upload_resp.json()["id"]

    get_resp = client.get(f"/api/v1/files/{file_id}", headers=auth_headers(token))
    assert get_resp.status_code == 200
    assert get_resp.content == _png_bytes()


def test_cross_tenant_cannot_access_another_orgs_file(client, org_a: OrgFixture, org_b: OrgFixture):
    org_a_token = org_a.teacher_token(client)
    upload_resp = client.post(
        "/api/v1/files",
        headers=auth_headers(org_a_token),
        files={"file": ("test.png", io.BytesIO(_png_bytes()), "image/png")},
    )
    file_id = upload_resp.json()["id"]

    org_b_token = org_b.teacher_token(client)
    get_resp = client.get(f"/api/v1/files/{file_id}", headers=auth_headers(org_b_token))
    assert get_resp.status_code == 404


def test_student_can_also_upload_images(client, org_a: OrgFixture):
    token = org_a.student_token(client)
    resp = client.post(
        "/api/v1/files",
        headers=auth_headers(token),
        files={"file": ("test.png", io.BytesIO(_png_bytes()), "image/png")},
    )
    assert resp.status_code == 201


def test_upload_returns_503_when_private_storage_backend_is_unavailable(client, org_a: OrgFixture, monkeypatch):
    import app.services.file_service as file_service_module

    class UnavailableStorage:
        def save(self, *_args, **_kwargs):
            raise StorageUnavailableError("unavailable")

    monkeypatch.setattr(file_service_module, "get_storage_service", lambda: UnavailableStorage())
    token = org_a.teacher_token(client)
    response = client.post(
        "/api/v1/files",
        headers=auth_headers(token),
        files={"file": ("test.png", io.BytesIO(_png_bytes()), "image/png")},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "File storage is temporarily unavailable. Please try again later."
