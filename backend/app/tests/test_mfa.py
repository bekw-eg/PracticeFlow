from datetime import datetime, timezone

from app.core.config import settings
from app.models.enums import RoleName
from app.models.membership import OrganizationMembership
from app.models.mfa_credential import MfaCredential
from app.models.role import Role
from app.models.user import User
from app.rate_limit.dependencies import get_mfa_rate_limiter
from app.services.auth_service import AuthService
from app.services.mfa_service import MfaService
from app.tests.conftest import DEV_PASSWORD, OrgFixture, auth_headers


def _promote_to_director(db, org: OrgFixture) -> OrganizationMembership:
    role = db.query(Role).filter_by(name=RoleName.DIRECTOR.value).one_or_none()
    if role is None:
        role = Role(name=RoleName.DIRECTOR.value)
        db.add(role)
        db.flush()
    membership = db.query(OrganizationMembership).filter_by(user_id=org.teacher_user.id, organization_id=org.org.id).one()
    membership.role_id = role.id
    db.commit()
    db.refresh(membership)
    return membership


def _current_code(secret: str) -> str:
    return MfaService._totp(secret, MfaService._totp_counter(datetime.now(timezone.utc)))


def _begin_enrollment(client, org: OrgFixture) -> tuple[str, str]:
    login = client.post("/api/v1/auth/login", json={"email": org.teacher_user.email, "password": DEV_PASSWORD, "organization_slug": org.org.slug})
    assert login.status_code == 202, login.text
    challenge_id = login.json()["challenge_id"]
    start = client.post("/api/v1/auth/mfa/enrollment/start", json={"challenge_id": challenge_id})
    assert start.status_code == 200, start.text
    return challenge_id, start.json()["manual_key"]


def test_privileged_password_login_requires_totp_before_tokens(client, db, org_a: OrgFixture):
    _promote_to_director(db, org_a)

    challenge_id, secret = _begin_enrollment(client, org_a)
    complete = client.post("/api/v1/auth/mfa/enrollment/verify", json={"challenge_id": challenge_id, "code": _current_code(secret)})

    assert complete.status_code == 200, complete.text
    assert complete.json()["access_token"]
    assert len(complete.json()["recovery_codes"]) == 10
    assert settings.REFRESH_COOKIE_NAME in complete.headers["set-cookie"]
    assert client.get("/api/v1/auth/me", headers=auth_headers(complete.json()["access_token"])).json()["role"] == "DIRECTOR"


def test_recovery_code_is_one_time_and_forces_new_enrollment(client, db, org_a: OrgFixture):
    _promote_to_director(db, org_a)
    challenge_id, secret = _begin_enrollment(client, org_a)
    enrolled = client.post("/api/v1/auth/mfa/enrollment/verify", json={"challenge_id": challenge_id, "code": _current_code(secret)}).json()
    recovery_code = enrolled["recovery_codes"][0]

    relogin = client.post("/api/v1/auth/login", json={"email": org_a.teacher_user.email, "password": DEV_PASSWORD, "organization_slug": org_a.org.slug})
    assert relogin.status_code == 202
    recovery = client.post("/api/v1/auth/mfa/recovery/verify", json={"challenge_id": relogin.json()["challenge_id"], "recovery_code": recovery_code})
    assert recovery.status_code == 200, recovery.text
    assert recovery.json()["status"] == "MFA_ENROLLMENT_REQUIRED"
    # The old MFA-bound token cannot survive resetting the factor.
    assert client.get("/api/v1/auth/me", headers=auth_headers(enrolled["access_token"])).status_code == 401


class _MfaLimiter:
    def __init__(self):
        self.failures = 0

    def is_blocked(self, key: str) -> bool:
        return self.failures >= 2

    def record_failure(self, key: str) -> None:
        self.failures += 1

    def reset(self, key: str) -> None:
        self.failures = 0


def test_mfa_code_guesses_are_rate_limited(client, db, org_a: OrgFixture):
    _promote_to_director(db, org_a)
    challenge_id, _ = _begin_enrollment(client, org_a)
    limiter = _MfaLimiter()
    from app.main import app

    app.dependency_overrides[get_mfa_rate_limiter] = lambda: limiter
    try:
        assert client.post("/api/v1/auth/mfa/enrollment/verify", json={"challenge_id": challenge_id, "code": "000000"}).status_code == 401
        assert client.post("/api/v1/auth/mfa/enrollment/verify", json={"challenge_id": challenge_id, "code": "000000"}).status_code == 401
        assert client.post("/api/v1/auth/mfa/enrollment/verify", json={"challenge_id": challenge_id, "code": "000000"}).status_code == 429
    finally:
        app.dependency_overrides.pop(get_mfa_rate_limiter, None)


def test_privileged_access_token_without_current_mfa_factor_is_rejected(client, db, org_a: OrgFixture):
    membership = _promote_to_director(db, org_a)
    secret = MfaService._new_secret()
    credential = MfaCredential(
        user_id=org_a.teacher_user.id,
        secret_encrypted=MfaService(db)._encrypt(secret),
        enabled_at=datetime.now(timezone.utc),
        security_version=3,
    )
    db.add(credential)
    db.commit()
    # A hand-issued old/non-MFA JWT cannot claim a new privileged role.
    from app.core.security import create_access_token

    token = create_access_token(org_a.teacher_user.id, membership.organization_id, RoleName.DIRECTOR.value)
    assert client.get("/api/v1/auth/me", headers=auth_headers(token)).status_code == 401


def _super_admin_with_factor(db, org: OrgFixture, email: str) -> tuple[User, OrganizationMembership, MfaCredential]:
    role = db.query(Role).filter_by(name=RoleName.SUPER_ADMIN.value).one_or_none()
    if role is None:
        role = Role(name=RoleName.SUPER_ADMIN.value)
        db.add(role)
        db.flush()
    user = User(email=email, hashed_password=org.teacher_user.hashed_password, full_name=email.split("@")[0])
    db.add(user)
    db.flush()
    membership = OrganizationMembership(user_id=user.id, organization_id=org.org.id, role_id=role.id)
    db.add(membership)
    db.flush()
    credential = MfaCredential(
        user_id=user.id,
        secret_encrypted=MfaService(db)._encrypt(MfaService._new_secret()),
        enabled_at=datetime.now(timezone.utc),
        security_version=1,
    )
    db.add(credential)
    db.commit()
    return user, membership, credential


def test_super_admin_peer_recovery_is_same_tenant_and_needs_another_approver(client, db, org_a: OrgFixture, org_b: OrgFixture):
    target, _, _ = _super_admin_with_factor(db, org_a, "target-super-admin@org-a.edu")
    approver, approver_membership, approver_credential = _super_admin_with_factor(db, org_a, "approver-super-admin@org-a.edu")
    outsider, outsider_membership, outsider_credential = _super_admin_with_factor(db, org_b, "outsider-super-admin@org-b.edu")

    login = client.post("/api/v1/auth/login", json={"email": target.email, "password": DEV_PASSWORD, "organization_slug": org_a.org.slug})
    assert login.status_code == 202
    challenge_id = login.json()["challenge_id"]
    requested = client.post("/api/v1/auth/mfa/recovery/peer-request", json={"challenge_id": challenge_id})
    assert requested.status_code == 200

    outsider_token, _ = AuthService(db)._issue_tokens(outsider.id, outsider_membership.organization_id, RoleName.SUPER_ADMIN.value, mfa_verified=True, mfa_security_version=outsider_credential.security_version)
    db.commit()
    assert client.post(f"/api/v1/management/mfa-recovery-requests/{challenge_id}/approve", headers=auth_headers(outsider_token)).status_code == 404

    approver_token, _ = AuthService(db)._issue_tokens(approver.id, approver_membership.organization_id, RoleName.SUPER_ADMIN.value, mfa_verified=True, mfa_security_version=approver_credential.security_version)
    db.commit()
    assert client.post(f"/api/v1/management/mfa-recovery-requests/{challenge_id}/approve", headers=auth_headers(approver_token)).status_code == 204
    assert client.get(f"/api/v1/auth/mfa/recovery/peer-status/{challenge_id}").json()["approved"] is True

    replacement = client.post("/api/v1/auth/mfa/recovery/complete-peer", json={"challenge_id": challenge_id})
    assert replacement.status_code == 200
    assert replacement.json()["status"] == "MFA_ENROLLMENT_REQUIRED"
    assert "access_token" not in replacement.json()
