import pytest
from pydantic import ValidationError

from app.core.config import Settings


def _production_settings(**overrides):
    values = {
        "ENV": "production",
        "DATABASE_URL": "postgresql+psycopg://app:strong-password@database:5432/practiceflow_prod",
        "DATABASE_POOL_SIZE": 10,
        "DATABASE_MAX_OVERFLOW": 5,
        "DATABASE_POOL_TIMEOUT_SECONDS": 30,
        "DATABASE_POOL_RECYCLE_SECONDS": 1800,
        "WORKER_DATABASE_POOL_SIZE": 2,
        "WORKER_DATABASE_MAX_OVERFLOW": 0,
        "WORKER_DATABASE_POOL_TIMEOUT_SECONDS": 15,
        "WORKER_DATABASE_POOL_RECYCLE_SECONDS": 1800,
        "JWT_SECRET_KEY": "a-production-secret-with-more-than-32-bytes",
        "CORS_ORIGINS": ["https://practice.example"],
        "SEED_ON_START": False,
        "COOKIE_SECURE": True,
        "LOGIN_RATE_LIMIT_BACKEND": "redis",
        "REDIS_URL": "redis://redis:6379/0",
        "RESOURCE_GUARD_BACKEND": "redis",
        "EXPORT_QUEUE_BACKEND": "redis",
        "STORAGE_BACKEND": "s3",
        "S3_ENDPOINT_URL": "https://objects.practice.example",
        "S3_BUCKET": "practiceflow-private",
        "S3_REGION": "us-east-1",
        "S3_ACCESS_KEY_ID": "production-access-key",
        "S3_SECRET_ACCESS_KEY": "production-secret-key",
        "S3_ADDRESSING_STYLE": "virtual",
        "S3_VERIFY_TLS": True,
        "UPLOAD_MAX_FILE_BYTES": 5 * 1024 * 1024,
        "UPLOAD_RATE_LIMIT_REQUESTS": 20,
        "UPLOAD_RATE_LIMIT_WINDOW_SECONDS": 60,
        "UPLOAD_USER_MAX_FILES": 100,
        "UPLOAD_USER_MAX_BYTES": 100 * 1024 * 1024,
        "UPLOAD_USER_QUOTA_WINDOW_SECONDS": 24 * 60 * 60,
        "UPLOAD_ORGANIZATION_MAX_STORAGE_BYTES": 5 * 1024 * 1024 * 1024,
        "UPLOAD_RESERVATION_TTL_SECONDS": 15 * 60,
        "UPLOAD_QUOTA_RETRY_AFTER_SECONDS": 60,
        "EXPORT_USER_RATE_LIMIT_REQUESTS": 10,
        "EXPORT_ORGANIZATION_RATE_LIMIT_REQUESTS": 60,
        "EXPORT_RATE_LIMIT_WINDOW_SECONDS": 60,
        "EXPORT_MAX_CONCURRENT_PER_USER": 1,
        "EXPORT_MAX_CONCURRENT_PER_ORGANIZATION": 3,
        "EXPORT_TIMEOUT_SECONDS": 45,
        "EXPORT_JOB_RETENTION_SECONDS": 24 * 60 * 60,
        "EXPORT_WORKER_LEASE_SECONDS": 75,
        "EXPORT_WORKER_HARD_TIMEOUT_SECONDS": 45,
        "EXPORT_WORKER_QUEUE_TIMEOUT_SECONDS": 5,
        "EXPORT_WORKER_REQUEUE_DELAY_SECONDS": 1,
        "EXPORT_WORKER_HEARTBEAT_INTERVAL_SECONDS": 15,
        "EXPORT_WORKER_HEARTBEAT_TTL_SECONDS": 90,
        "DOCUMENT_CHECK_WORKER_POLL_SECONDS": 1,
        "DOCUMENT_CHECK_WORKER_TIMEOUT_SECONDS": 60,
        "DOCUMENT_CHECK_WORKER_LEASE_SECONDS": 120,
        "DOCUMENT_CHECK_WORKER_MAX_ATTEMPTS": 3,
        "DOCUMENT_CHECK_MAX_FINDINGS": 5000,
        "LOCAL_PLAGIARISM_MIN_MATCH_WORDS": 8,
        "LOCAL_PLAGIARISM_MAX_MATCHES": 1000,
        "LOCAL_PLAGIARISM_MAX_CANDIDATE_DOCUMENTS": 500,
        "LOCAL_PLAGIARISM_MAX_INDEXED_WORDS": 100000,
        "TRUSTED_PROXY_IPS": "172.30.0.10,172.30.0.11",
        "MFA_TOTP_ENCRYPTION_KEY": "JQFzqBCnqc_YZjyDyObIEqomNrVDnpgymh2WryBuxSk=",
        "MFA_RECOVERY_CODE_PEPPER": "a-production-recovery-code-pepper-with-more-than-32-bytes",
        "MFA_BREAK_GLASS_KEY_A_HASH": "a" * 64,
        "MFA_BREAK_GLASS_KEY_B_HASH": "b" * 64,
        "AUDIT_HASH_PEPPER": "a-production-audit-hash-pepper-with-more-than-32-bytes",
        "AUDIT_RETENTION_DAYS": 365,
        "AUDIT_CLEANUP_INTERVAL_SECONDS": 6 * 60 * 60,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.mark.parametrize("secret", ["", "short", "default", "change-me-in-env"])
def test_production_rejects_missing_short_or_placeholder_jwt(secret):
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY"):
        _production_settings(JWT_SECRET_KEY=secret)


def test_production_rejects_seed_and_in_memory_rate_limit():
    with pytest.raises(ValidationError, match="SEED_ON_START"):
        _production_settings(SEED_ON_START=True)
    with pytest.raises(ValidationError, match="LOGIN_RATE_LIMIT_BACKEND"):
        _production_settings(LOGIN_RATE_LIMIT_BACKEND="memory")
    with pytest.raises(ValidationError, match="RESOURCE_GUARD_BACKEND"):
        _production_settings(RESOURCE_GUARD_BACKEND="memory")
    with pytest.raises(ValidationError, match="EXPORT_QUEUE_BACKEND"):
        _production_settings(EXPORT_QUEUE_BACKEND="memory")


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"DATABASE_POOL_SIZE": 0}, "Database pool sizes"),
        ({"DATABASE_MAX_OVERFLOW": -1}, "overflow"),
        ({"WORKER_DATABASE_POOL_TIMEOUT_SECONDS": 0}, "timeout and recycle"),
    ],
)
def test_production_requires_bounded_database_pool_settings(overrides, message):
    with pytest.raises(ValidationError, match=message):
        _production_settings(**overrides)


@pytest.mark.parametrize("trusted_proxies", ["", "*", "not-an-ip"])
def test_production_requires_an_explicit_valid_proxy_allow_list(trusted_proxies):
    with pytest.raises(ValidationError, match="TRUSTED_PROXY_IPS"):
        _production_settings(TRUSTED_PROXY_IPS=trusted_proxies)


def test_secure_production_configuration_is_accepted():
    configured = _production_settings()
    assert configured.is_production
    assert configured.COOKIE_SECURE is True


def test_production_rejects_unsafe_worker_heartbeat_timing():
    with pytest.raises(ValidationError, match="HEARTBEAT_INTERVAL"):
        _production_settings(EXPORT_WORKER_HEARTBEAT_INTERVAL_SECONDS=90)
    with pytest.raises(ValidationError, match="DOCUMENT_CHECK_WORKER_LEASE_SECONDS"):
        _production_settings(DOCUMENT_CHECK_WORKER_LEASE_SECONDS=60)


def test_production_requires_non_default_mfa_secrets_and_two_custodians():
    with pytest.raises(ValidationError, match="MFA_TOTP_ENCRYPTION_KEY"):
        _production_settings(MFA_TOTP_ENCRYPTION_KEY="HBty4TLVz8EFytDynjGd5lyW3Mw2u24MSaNGVrH2ON0=")
    with pytest.raises(ValidationError, match="MFA break-glass"):
        _production_settings(MFA_BREAK_GLASS_KEY_A_HASH=None)


def test_production_requires_a_separate_audit_pepper_and_explicit_retention():
    with pytest.raises(ValidationError, match="AUDIT_HASH_PEPPER"):
        _production_settings(AUDIT_HASH_PEPPER="short")
    with pytest.raises(ValidationError, match="[Aa]udit retention"):
        _production_settings(AUDIT_RETENTION_DAYS=0)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"STORAGE_BACKEND": "local"}, "STORAGE_BACKEND=s3"),
        ({"S3_BUCKET": None}, "S3_BUCKET"),
        ({"S3_ACCESS_KEY_ID": None}, "S3_ACCESS_KEY_ID"),
        ({"S3_ENDPOINT_URL": "http://objects.practice.example"}, "HTTPS endpoint"),
        ({"S3_VERIFY_TLS": False}, "HTTPS endpoint"),
    ],
)
def test_production_requires_complete_private_s3_storage_configuration(overrides, message):
    with pytest.raises(ValidationError, match=message):
        _production_settings(**overrides)
