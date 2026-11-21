from app.core.config import settings
from app.main import app
from app.tests.conftest import OrgFixture, auth_headers


def test_me_exposes_product_migration_flags(client, org_a: OrgFixture, monkeypatch):
    monkeypatch.setattr(settings, "DOCUMENT_CHECK_ENABLED", False)

    response = client.get(
        "/api/v1/auth/me",
        headers=auth_headers(org_a.teacher_token(client)),
    )

    assert response.status_code == 200
    assert response.json()["features"] == {
        "document_check_enabled": False,
    }


def test_disabled_document_check_api_is_hidden(client, org_a: OrgFixture, monkeypatch):
    headers = auth_headers(org_a.teacher_token(client))
    monkeypatch.setattr(settings, "DOCUMENT_CHECK_ENABLED", False)

    response = client.get("/api/v1/check-profiles", headers=headers)

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "DOCUMENT_CHECK_DISABLED"


def test_legacy_routes_are_not_registered():
    paths = app.openapi()["paths"]

    for removed in ("/api/v1/templates", "/api/v1/reports", "/api/v1/internships/{internship_id}/publish", "/api/v1/files", "/api/v1/export-jobs/{job_id}"):
        assert removed not in paths
    assert "get" in paths["/api/v1/check-profiles"]
