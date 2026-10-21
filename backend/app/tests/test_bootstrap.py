import io
import json
import os
import secrets
import subprocess
import sys
import warnings
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.cli import bootstrap as cli
from app.core.config import settings
from app.core.security import create_access_token, decode_token, hash_password, verify_password
from app.models.audit_log import AuditLog
from app.models.enums import AuditEventType, RoleName
from app.models.membership import OrganizationMembership
from app.models.mfa_credential import MfaCredential
from app.models.organization import Organization
from app.models.refresh_token import RefreshToken
from app.models.role import Role
from app.models.user import User
from app.services.audit_service import AuditService
from app.services.bootstrap_service import BootstrapConflict, BootstrapIdentity, bootstrap
from app.services.mfa_service import MfaService
from app.tests.conftest import TEST_DATABASE_URL, auth_headers, engine
from app.tests.test_config import _production_settings


@pytest.fixture
def identity():
    return BootstrapIdentity(
        organization_name="Example Academy", organization_slug="example-academy",
        admin_email="first-admin@example.org", admin_full_name="Example Operator",
    )


@pytest.fixture
def password():
    return secrets.token_urlsafe(24)


def _counts(db):
    return tuple(db.scalar(select(func.count()).select_from(model)) for model in (
        Role, Organization, User, OrganizationMembership, AuditLog, MfaCredential, RefreshToken,
    ))


def _unexpected_password():
    pytest.fail("Conflicts and repeats must not request a password")


def test_empty_database_and_exact_repeat_preserve_password_audit_and_mfa(db, identity, password):
    result = bootstrap(db, identity, lambda: password)
    assert result.created
    assert _counts(db) == (4, 1, 1, 1, 2, 0, 0)
    user = db.get(User, result.user_id)
    original_hash = user.hashed_password
    assert original_hash != password and verify_password(password, original_hash)
    membership = db.scalar(select(OrganizationMembership))
    assert membership.is_active and membership.role.name == "SUPER_ADMIN"
    assert AuditService(db).verify(result.organization_id).valid
    assert {event.event_type for event in db.scalars(select(AuditLog))} == {
        AuditEventType.ORGANIZATION_CREATED, AuditEventType.MEMBERSHIP_CREATED,
    }
    db.rollback()
    repeat = bootstrap(db, identity, _unexpected_password)
    assert not repeat.created and repeat.user_id == result.user_id
    assert _counts(db) == (4, 1, 1, 1, 2, 0, 0)
    assert db.get(User, result.user_id).hashed_password == original_hash


@pytest.mark.parametrize("conflict", ["user", "mixed_case_email", "organization", "other_organization", "student", "inactive_user", "inactive_membership", "changed_name", "changed_full_name"])
def test_existing_data_is_never_adopted_promoted_reset_or_reactivated(db, identity, password, conflict):
    if conflict in {"user", "mixed_case_email"}:
        email = identity.admin_email if conflict == "user" else str(identity.admin_email).upper()
        db.add(User(email=email, full_name=identity.admin_full_name, hashed_password=hash_password(password)))
        db.commit()
    elif conflict in {"organization", "other_organization"}:
        slug = identity.organization_slug if conflict == "organization" else "unrelated-academy"
        db.add(Organization(name=identity.organization_name, slug=slug))
        db.commit()
    else:
        result = bootstrap(db, identity, lambda: password)
        if conflict == "student":
            membership = db.scalar(select(OrganizationMembership))
            membership.role_id = db.scalar(select(Role.id).where(Role.name == "STUDENT"))
        elif conflict == "inactive_user":
            db.get(User, result.user_id).is_active = False
        elif conflict == "inactive_membership":
            db.scalar(select(OrganizationMembership)).is_active = False
        elif conflict == "changed_name":
            db.get(Organization, result.organization_id).name = "Renamed Academy"
        else:
            db.get(User, result.user_id).full_name = "Renamed Operator"
        db.commit()
    before = _counts(db)
    hashes = list(db.scalars(select(User.hashed_password)))
    roles = list(db.scalars(select(OrganizationMembership.role_id)))
    active = list(db.scalars(select(User.is_active)))
    membership_active = list(db.scalars(select(OrganizationMembership.is_active)))
    db.rollback()
    with pytest.raises(BootstrapConflict, match="existing identities"):
        bootstrap(db, identity, _unexpected_password)
    assert _counts(db) == before
    assert list(db.scalars(select(User.hashed_password))) == hashes
    assert list(db.scalars(select(OrganizationMembership.role_id))) == roles
    assert list(db.scalars(select(User.is_active))) == active
    assert list(db.scalars(select(OrganizationMembership.is_active))) == membership_active


def test_preexisting_role_catalog_is_reused_without_editing_it(db, identity, password):
    role = Role(name=RoleName.SUPER_ADMIN.value, description="Existing catalog entry")
    db.add(role)
    db.commit()
    role_id = role.id
    db.rollback()
    bootstrap(db, identity, lambda: password)
    assert _counts(db) == (4, 1, 1, 1, 2, 0, 0)
    assert db.get(Role, role_id).description == "Existing catalog entry"
    assert db.scalar(select(OrganizationMembership)).role_id == role_id


def test_audit_failure_rolls_back_every_bootstrap_write(db, identity, password, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("simulated persistence failure")

    monkeypatch.setattr(AuditService, "record", fail)
    with pytest.raises(RuntimeError, match="simulated"):
        bootstrap(db, identity, lambda: password)
    assert _counts(db) == (0, 0, 0, 0, 0, 0, 0)


@pytest.mark.parametrize("length", [0, 7, 73])
def test_password_policy_rejects_invalid_lengths_without_writes(db, identity, length):
    with pytest.raises(ValueError, match="Password must"):
        bootstrap(db, identity, lambda: "x" * length)
    assert _counts(db) == (0, 0, 0, 0, 0, 0, 0)


def test_concurrent_different_bootstraps_cannot_create_a_second_tenant(identity, password):
    entered = Event()
    release = Event()
    second_started = Event()

    def first_password():
        entered.set()
        assert release.wait(4)
        return password

    def run(target, provider, started=None):
        if started:
            started.set()
        with Session(engine) as session:
            return bootstrap(session, target, provider)

    other = identity.model_copy(update={"organization_slug": "second-academy", "admin_email": "second-admin@example.org"})
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(run, identity, first_password)
        assert entered.wait(4)
        second = pool.submit(run, other, _unexpected_password, second_started)
        assert second_started.wait(4)
        release.set()
        assert first.result(timeout=10).created
        with pytest.raises(BootstrapConflict):
            second.result(timeout=10)
    with Session(engine) as session:
        assert _counts(session) == (4, 1, 1, 1, 2, 0, 0)


def _arguments(identity):
    return [
        "--organization-name", identity.organization_name,
        "--organization-slug", identity.organization_slug,
        "--admin-email", str(identity.admin_email),
        "--admin-full-name", identity.admin_full_name,
        "--password-stdin",
    ]


def _production_env():
    configured = _production_settings(DATABASE_URL=TEST_DATABASE_URL)
    env = os.environ.copy()
    for key, value in configured.model_dump(mode="json").items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = json.dumps(value) if not isinstance(value, str) else value
    return env


def _command(identity, password, env):
    return subprocess.run(
        [sys.executable, "-m", "app.cli.bootstrap", *_arguments(identity)],
        input=password, text=True, capture_output=True, check=False,
        cwd=Path(__file__).resolve().parents[2], env=env, timeout=30,
    )


def test_production_cli_stdin_repeat_conflict_and_first_login_mfa(client, db, identity, password, monkeypatch):
    env = _production_env()
    created = _command(identity, password + "\n", env)
    assert created.returncode == 0, created.stderr
    assert "MFA enrollment is required" in created.stdout
    assert password not in created.stdout + created.stderr
    repeated = _command(identity, "", env)
    assert repeated.returncode == 0, repeated.stderr
    assert "No changes made" in repeated.stdout
    conflict = _command(identity.model_copy(update={"admin_email": "other-admin@example.org"}), "", env)
    assert conflict.returncode == 1 and "Bootstrap refused" in conflict.stderr

    # HTTPS cookie semantics and the real login/enrollment routes, using only
    # the dedicated test database; production Redis/S3 are never contacted.
    import httpx

    monkeypatch.setattr(settings, "COOKIE_SECURE", True)
    client.base_url = httpx.URL("https://testserver")
    payload = {"email": str(identity.admin_email), "password": password, "organization_slug": identity.organization_slug}
    wrong = client.post("/api/v1/auth/login", json={**payload, "password": secrets.token_urlsafe(24)})
    assert wrong.status_code == 401
    login = client.post("/api/v1/auth/login", json=payload)
    assert login.status_code == 202
    assert login.json()["status"] == "MFA_ENROLLMENT_REQUIRED"
    assert "access_token" not in login.json() and "refresh_token" not in login.json()
    assert settings.REFRESH_COOKIE_NAME not in client.cookies
    assert "Secure" in login.headers["set-cookie"] and "HttpOnly" in login.headers["set-cookie"]
    assert client.get("/api/v1/auth/me").status_code == 401
    user = db.scalar(select(User))
    org = db.scalar(select(Organization))
    token = create_access_token(user.id, org.id, "SUPER_ADMIN")
    assert client.get("/api/v1/auth/me", headers=auth_headers(token)).status_code == 401
    challenge = login.json()["challenge_id"]
    enrollment = client.post("/api/v1/auth/mfa/enrollment/start", json={"challenge_id": challenge})
    assert enrollment.status_code == 200
    secret = enrollment.json()["manual_key"]
    code = MfaService._totp(secret, MfaService._totp_counter())
    completed = client.post("/api/v1/auth/mfa/enrollment/verify", json={"challenge_id": challenge, "code": code})
    assert completed.status_code == 200
    assert len(completed.json()["recovery_codes"]) == 10
    access = completed.json()["access_token"]
    assert decode_token(access)["mfa_verified"] is True
    assert client.get("/api/v1/auth/me", headers=auth_headers(access)).json()["role"] == "SUPER_ADMIN"
    original_hash = user.hashed_password
    credential = db.scalar(select(MfaCredential))
    credential_state = (credential.id, credential.secret_encrypted, credential.security_version)
    db.rollback()
    assert _command(identity, "", env).returncode == 0
    assert db.get(User, user.id).hashed_password == original_hash
    db.refresh(credential)
    assert (credential.id, credential.secret_encrypted, credential.security_version) == credential_state
    relogin = client.post("/api/v1/auth/login", json=payload)
    assert relogin.status_code == 202 and relogin.json()["status"] == "MFA_REQUIRED"


@pytest.mark.parametrize("setting,value", [("SEED_ON_START", "true"), ("COOKIE_SECURE", "false"), ("LOGIN_RATE_LIMIT_BACKEND", "memory"), ("MFA_TOTP_ENCRYPTION_KEY", "invalid"), ("JWT_SECRET_KEY", "short")])
def test_cli_preserves_production_configuration_checks(identity, password, setting, value):
    env = _production_env()
    env[setting] = value
    result = _command(identity, password, env)
    assert result.returncode == 1
    assert "Invalid configuration" in result.stderr
    assert password not in result.stdout + result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("environment", ["development", "test", "e2e"])
def test_cli_requires_explicit_production_environment(db, identity, environment):
    env = _production_env()
    env["ENV"] = environment
    result = _command(identity, "", env)
    assert result.returncode == 1
    assert "requires ENV=production" in result.stderr
    assert _counts(db) == (0, 0, 0, 0, 0, 0, 0)


@pytest.mark.parametrize("supplied", ["", "short", "x" * 73, "я" * 37, "valid-length\nsecond-line\n"])
def test_cli_rejects_bad_stdin_without_exposing_it(db, identity, supplied, monkeypatch, capsys):
    monkeypatch.setattr(settings, "DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setattr(settings, "ENV", "production")
    monkeypatch.setattr(sys, "stdin", io.StringIO(supplied))
    assert cli.main(_arguments(identity)) == 1
    output = capsys.readouterr()
    assert "Password input rejected" in output.err
    if supplied:
        assert supplied not in output.out + output.err
    assert _counts(db) == (0, 0, 0, 0, 0, 0, 0)


def test_hidden_password_confirmation_and_no_echo_fallback(password, monkeypatch):
    values = iter([password, password])
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt: next(values))
    assert cli.read_password(password_stdin=False) == password
    values = iter([password, password + "different"])
    with pytest.raises(cli.BootstrapInputError, match="do not match"):
        cli.read_password(password_stdin=False)

    def unsafe(prompt):
        warnings.warn("unsafe console", cli.getpass.GetPassWarning)
        pytest.fail("must not read an echoed password")

    monkeypatch.setattr(cli.getpass, "getpass", unsafe)
    with pytest.raises(cli.BootstrapInputError, match="Hidden terminal input is unavailable"):
        cli.read_password(password_stdin=False)


def test_argument_errors_never_echo_accidentally_supplied_secrets(password, capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--password", password])
    assert exc.value.code == 2
    assert password not in capsys.readouterr().err


def test_busy_database_returns_actionable_error_without_sql(identity, monkeypatch, capsys):
    monkeypatch.setattr(settings, "DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setattr(settings, "ENV", "production")
    with engine.begin() as connection:
        connection.execute(text("LOCK TABLE users IN SHARE ROW EXCLUSIVE MODE"))
        assert cli.main(_arguments(identity)) == 1
    output = capsys.readouterr()
    assert "Database is busy" in output.err
    assert "LOCK TABLE" not in output.err and "Traceback" not in output.err
