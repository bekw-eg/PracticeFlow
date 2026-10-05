from app.core.config import settings
from app.main import app
from app.tests.conftest import OrgFixture, auth_headers


def test_me_exposes_product_migration_flags(client, org_a: OrgFixture, monkeypatch):
    monkeypatch.setattr(settings, "DOCUMENT_CHECK_ENABLED", False)
    monkeypatch.setattr(settings, "LEGACY_DOCUMENT_EDITOR_ENABLED", True)

    response = client.get(
        "/api/v1/auth/me",
        headers=auth_headers(org_a.teacher_token(client)),
    )

    assert response.status_code == 200
    assert response.json()["features"] == {
        "document_check_enabled": False,
        "legacy_document_editor_enabled": True,
    }


def test_disabled_document_check_api_is_hidden(client, org_a: OrgFixture, monkeypatch):
    headers = auth_headers(org_a.teacher_token(client))
    monkeypatch.setattr(settings, "DOCUMENT_CHECK_ENABLED", False)

    response = client.get("/api/v1/check-profiles", headers=headers)

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "DOCUMENT_CHECK_DISABLED"


def test_legacy_archive_stays_readable_when_authoring_is_frozen(
    client, org_a: OrgFixture, monkeypatch
):
    headers = auth_headers(org_a.teacher_token(client))
    monkeypatch.setattr(settings, "LEGACY_DOCUMENT_EDITOR_ENABLED", False)

    list_response = client.get("/api/v1/templates", headers=headers)
    create_response = client.post(
        "/api/v1/templates",
        headers=headers,
        json={"name": "Must not be created"},
    )

    assert list_response.status_code == 200
    assert len(list_response.json()) == 1
    assert create_response.status_code == 409
    assert create_response.json()["detail"]["code"] == "LEGACY_DOCUMENT_EDITOR_DISABLED"


def test_legacy_routes_are_deprecated_in_openapi():
    schema = app.openapi()

    assert schema["paths"]["/api/v1/templates"]["get"]["deprecated"] is True
    assert schema["paths"]["/api/v1/reports"]["get"]["deprecated"] is True
    assert "deprecated" not in schema["paths"]["/api/v1/check-profiles"]["get"]
