from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.models.membership import OrganizationMembership
from app.rate_limit.dependencies import get_login_rate_limiter
from app.services.access_link_service import AccessLinkService
from app.tests.conftest import DEV_PASSWORD, OrgFixture, auth_headers


def test_login_success(client, org_a: OrgFixture):
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": org_a.teacher_user.email, "password": DEV_PASSWORD, "organization_slug": org_a.org.slug},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" not in body
    set_cookie = resp.headers["set-cookie"]
    assert settings.REFRESH_COOKIE_NAME in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie


def test_login_wrong_password(client, org_a: OrgFixture):
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": org_a.teacher_user.email, "password": "wrong-password", "organization_slug": org_a.org.slug},
    )
    assert resp.status_code == 401


def test_login_wrong_org_slug(client, org_a: OrgFixture):
    """A valid user/password combo for the wrong organization must fail —
    proves login itself is tenant-aware, not just post-login access."""
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": org_a.teacher_user.email, "password": DEV_PASSWORD, "organization_slug": "nonexistent-org"},
    )
    assert resp.status_code == 401


def test_user_of_org_a_cannot_login_to_org_b(client, org_a: OrgFixture, org_b: OrgFixture):
    """org_a's teacher has no membership in org_b — logging in against org_b's
    slug with org_a's credentials must fail even though the password is correct."""
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": org_a.teacher_user.email, "password": DEV_PASSWORD, "organization_slug": org_b.org.slug},
    )
    assert resp.status_code == 401


def test_me_returns_correct_identity(client, org_a: OrgFixture):
    token = org_a.teacher_token(client)
    resp = client.get("/api/v1/auth/me", headers=auth_headers(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == org_a.teacher_user.email
    assert body["role"] == "TEACHER"
    assert body["organization_id"] == str(org_a.org.id)


def test_no_token_returns_401(client):
    resp = client.get("/api/v1/groups")
    assert resp.status_code == 401


def test_garbage_token_returns_401(client):
    resp = client.get("/api/v1/groups", headers=auth_headers("not-a-real-token"))
    assert resp.status_code == 401


def test_refresh_issues_new_tokens(client, org_a: OrgFixture):
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": org_a.teacher_user.email, "password": DEV_PASSWORD, "organization_slug": org_a.org.slug},
    )
    old_refresh = client.cookies.get(settings.REFRESH_COOKIE_NAME)
    assert old_refresh
    resp = client.post("/api/v1/auth/refresh")
    assert resp.status_code == 200
    new_tokens = resp.json()
    assert new_tokens["access_token"] != login_resp.json()["access_token"]
    assert "refresh_token" not in new_tokens
    assert client.cookies.get(settings.REFRESH_COOKIE_NAME) != old_refresh

    # Old refresh token must now be revoked (rotation) — reusing it must fail.
    with TestClient(app, cookies={settings.REFRESH_COOKIE_NAME: old_refresh}) as replay_client:
        reuse_resp = replay_client.post("/api/v1/auth/refresh")
        assert reuse_resp.status_code == 401


def test_logout_revokes_refresh_token(client, org_a: OrgFixture):
    client.post(
        "/api/v1/auth/login",
        json={"email": org_a.teacher_user.email, "password": DEV_PASSWORD, "organization_slug": org_a.org.slug},
    )
    refresh_token = client.cookies.get(settings.REFRESH_COOKIE_NAME)
    logout_resp = client.post("/api/v1/auth/logout")
    assert logout_resp.status_code == 204
    assert client.cookies.get(settings.REFRESH_COOKIE_NAME) is None

    with TestClient(app, cookies={settings.REFRESH_COOKIE_NAME: refresh_token}) as replay_client:
        reuse_resp = replay_client.post("/api/v1/auth/refresh")
        assert reuse_resp.status_code == 401


def test_refresh_without_cookie_returns_401(client):
    client.cookies.clear()
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_refresh_does_not_switch_tenant_when_original_membership_is_revoked(
    client,
    db,
    org_a: OrgFixture,
    org_b: OrgFixture,
):
    # Give the same user another valid organization, then revoke the one that
    # issued the cookie. Refresh must fail rather than selecting org_b.
    db.add(
        OrganizationMembership(
            user_id=org_a.teacher_user.id,
            organization_id=org_b.org.id,
            role_id=org_b.role_teacher.id,
        )
    )
    db.commit()
    client.post(
        "/api/v1/auth/login",
        json={"email": org_a.teacher_user.email, "password": DEV_PASSWORD, "organization_slug": org_a.org.slug},
    )
    original = db.query(OrganizationMembership).filter_by(
        user_id=org_a.teacher_user.id,
        organization_id=org_a.org.id,
    ).one()
    original.is_active = False
    db.commit()

    response = client.post("/api/v1/auth/refresh")
    assert response.status_code == 401


def test_password_longer_than_bcrypt_limit_is_rejected(client, org_a: OrgFixture):
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": org_a.teacher_user.email,
            "password": "ү" * 37,  # 74 UTF-8 bytes
            "organization_slug": org_a.org.slug,
        },
    )
    assert response.status_code == 422


class _FakeLimiter:
    def __init__(self):
        self.failures = 0

    def is_blocked(self, key: str) -> bool:
        return self.failures >= 2

    def record_failure(self, key: str) -> None:
        self.failures += 1

    def reset(self, key: str) -> None:
        self.failures = 0


def test_login_rate_limiter_is_injectable_and_blocks_failures(client, org_a: OrgFixture):
    limiter = _FakeLimiter()
    app.dependency_overrides[get_login_rate_limiter] = lambda: limiter
    payload = {"email": org_a.teacher_user.email, "password": "bad-password", "organization_slug": org_a.org.slug}

    assert client.post("/api/v1/auth/login", json=payload).status_code == 401
    assert client.post("/api/v1/auth/login", json=payload).status_code == 401
    assert client.post("/api/v1/auth/login", json=payload).status_code == 429


def test_password_reset_request_sends_an_access_link_for_an_active_membership(client, org_a: OrgFixture, monkeypatch):
    created: list[tuple[str, str]] = []
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.test")
    monkeypatch.setattr(
        AccessLinkService,
        "create",
        lambda _self, user, organization_id, purpose: created.append((user.email, purpose)),
    )

    response = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": org_a.student_user.email, "organization_slug": org_a.org.slug},
    )

    assert response.status_code == 202
    assert created == [(org_a.student_user.email, "PASSWORD_RESET")]


def test_password_reset_request_does_not_reveal_or_create_links_for_unknown_users(client, org_a: OrgFixture, monkeypatch):
    created: list[tuple[str, str]] = []
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.test")
    monkeypatch.setattr(
        AccessLinkService,
        "create",
        lambda _self, user, organization_id, purpose: created.append((user.email, purpose)),
    )

    response = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "unknown@example.edu", "organization_slug": org_a.org.slug},
    )

    assert response.status_code == 202
    assert created == []


class _PasswordResetLimiter:
    def __init__(self):
        self.failures: dict[str, int] = {}

    def is_blocked(self, key: str) -> bool:
        return self.failures.get(key, 0) >= 2

    def record_failure(self, key: str) -> None:
        self.failures[key] = self.failures.get(key, 0) + 1

    def reset(self, key: str) -> None:
        self.failures.pop(key, None)


def test_password_reset_request_is_rate_limited_without_disclosing_the_account(client, org_a: OrgFixture):
    limiter = _PasswordResetLimiter()
    app.dependency_overrides[get_login_rate_limiter] = lambda: limiter
    payload = {"email": org_a.student_user.email, "organization_slug": org_a.org.slug}

    assert client.post("/api/v1/auth/password-reset/request", json=payload).status_code == 202
    assert client.post("/api/v1/auth/password-reset/request", json=payload).status_code == 202
    response = client.post("/api/v1/auth/password-reset/request", json=payload)

    assert response.status_code == 429
