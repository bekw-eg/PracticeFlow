from functools import lru_cache
from ipaddress import IPv4Network, IPv6Network, ip_network
from typing import Literal
from urllib.parse import urlparse

from cryptography.fernet import Fernet
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_DEV_DATABASE_URL = "postgresql+psycopg://practiceflow:practiceflow@localhost:5432/practiceflow"
_DEV_MFA_FERNET_KEY = "HBty4TLVz8EFytDynjGd5lyW3Mw2u24MSaNGVrH2ON0="
_DEV_MFA_RECOVERY_PEPPER = "practiceflow-development-recovery-pepper-change-before-production"
_DEV_AUDIT_HASH_PEPPER = "practiceflow-development-audit-hash-pepper-change-before-production"
_PLACEHOLDER_SECRETS = {
    "changeme",
    "change-me-in-env",
    "default",
    "dev-secret-change-me-before-any-real-deployment",
    "placeholder",
    "replace-with-a-unique-64-character-random-secret",
    "secret",
}

TrustedProxyNetwork = IPv4Network | IPv6Network


def parse_trusted_proxy_ips(raw_value: str) -> tuple[TrustedProxyNetwork, ...]:
    """Parse a comma-separated allow-list of proxy addresses/CIDRs.

    A missing value intentionally means "trust no forwarded headers".  We do
    not accept a wildcard because it would reintroduce X-Forwarded-For spoofing.
    """

    entries = [entry.strip() for entry in raw_value.split(",") if entry.strip()]
    networks: list[TrustedProxyNetwork] = []
    for entry in entries:
        if entry == "*":
            raise ValueError("TRUSTED_PROXY_IPS must list explicit IP addresses or CIDRs; '*' is not allowed")
        try:
            networks.append(ip_network(entry, strict=False))
        except ValueError as exc:
            raise ValueError(f"TRUSTED_PROXY_IPS contains an invalid IP address or CIDR: {entry!r}") from exc
    return tuple(networks)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ENV: str = "development"
    PROJECT_NAME: str = "PracticeFlow"
    API_V1_PREFIX: str = "/api/v1"

    DATABASE_URL: str = _DEV_DATABASE_URL
    # API replicas hold bounded SQLAlchemy QueuePool connections.  Production
    # must set these explicitly so its PostgreSQL connection budget remains
    # predictable when replicas are added.
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 5
    DATABASE_POOL_TIMEOUT_SECONDS: int = 30
    DATABASE_POOL_RECYCLE_SECONDS: int = 30 * 60
    # The export worker is deliberately smaller than an API replica. Each
    # worker processes one renderer child at a time, so a large DB pool only
    # makes exhaustion under CPU pressure more likely.
    WORKER_DATABASE_POOL_SIZE: int = 2
    WORKER_DATABASE_MAX_OVERFLOW: int = 0
    WORKER_DATABASE_POOL_TIMEOUT_SECONDS: int = 15
    WORKER_DATABASE_POOL_RECYCLE_SECONDS: int = 30 * 60

    JWT_SECRET_KEY: str = "change-me-in-env"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    CORS_ORIGINS: list[str] = ["http://localhost:5173"]
    SEED_ON_START: bool = False

    # Migration controls. Both default to on so deploying this additive phase
    # cannot strand existing students before DOCX submission is available.
    DOCUMENT_CHECK_ENABLED: bool = True
    DOCUMENT_CHECK_STUDENT_SUBMISSIONS_ENABLED: bool = False
    LEGACY_DOCUMENT_EDITOR_ENABLED: bool = True

    REFRESH_COOKIE_NAME: str = "practiceflow_refresh"
    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"
    COOKIE_DOMAIN: str | None = None

    LOGIN_RATE_LIMIT_BACKEND: Literal["memory", "redis"] = "memory"
    REDIS_URL: str | None = None
    LOGIN_RATE_LIMIT_ATTEMPTS: int = 8
    LOGIN_RATE_LIMIT_WINDOW_SECONDS: int = 15 * 60
    TRUSTED_PROXY_IPS: str = ""

    # Resource-abuse protection deliberately has its own namespace and
    # configuration.  Development can use an in-process implementation, but
    # production must use the same Redis service as the authentication limiter
    # so a second backend replica cannot bypass quotas or export slots.
    RESOURCE_GUARD_BACKEND: Literal["memory", "redis"] = "memory"
    UPLOAD_MAX_FILE_BYTES: int = 5 * 1024 * 1024
    # DOCX preflight limits are separate from editor image upload limits.
    DOCX_MAX_UPLOAD_BYTES: int = Field(default=20 * 1024 * 1024, gt=0)
    DOCX_MAX_ZIP_ENTRIES: int = Field(default=2048, gt=0)
    DOCX_MAX_UNCOMPRESSED_BYTES: int = Field(default=100 * 1024 * 1024, gt=0)
    DOCX_MAX_ENTRY_BYTES: int = Field(default=20 * 1024 * 1024, gt=0)
    DOCX_MAX_COMPRESSION_RATIO: float = Field(default=200.0, gt=0, allow_inf_nan=False)
    DOCUMENT_CHECK_WORKER_POLL_SECONDS: float = Field(default=1.0, gt=0, le=60)
    DOCUMENT_CHECK_WORKER_TIMEOUT_SECONDS: int = Field(default=60, ge=1, le=3600)
    DOCUMENT_CHECK_WORKER_LEASE_SECONDS: int = Field(default=120, ge=10, le=7200)
    DOCUMENT_CHECK_WORKER_MAX_ATTEMPTS: int = Field(default=3, ge=1, le=20)
    DOCUMENT_CHECK_MAX_FINDINGS: int = Field(default=5000, ge=1, le=50000)
    # Local similarity compares one Teacher-uploaded DOCX only with indexed
    # originals of the same organization.  The bounds keep one scan from
    # consuming an unbounded amount of worker CPU or database memory.
    LOCAL_PLAGIARISM_MIN_MATCH_WORDS: int = Field(default=8, ge=3, le=100)
    LOCAL_PLAGIARISM_MAX_MATCHES: int = Field(default=300, ge=1, le=5000)
    LOCAL_PLAGIARISM_MAX_CANDIDATE_DOCUMENTS: int = Field(default=250, ge=1, le=5000)
    LOCAL_PLAGIARISM_MAX_INDEXED_WORDS: int = Field(default=100000, ge=1000, le=1000000)
    UPLOAD_RATE_LIMIT_REQUESTS: int = 20
    UPLOAD_RATE_LIMIT_WINDOW_SECONDS: int = 60
    UPLOAD_USER_MAX_FILES: int = 100
    UPLOAD_USER_MAX_BYTES: int = 100 * 1024 * 1024
    UPLOAD_USER_QUOTA_WINDOW_SECONDS: int = 24 * 60 * 60
    UPLOAD_ORGANIZATION_MAX_STORAGE_BYTES: int = 5 * 1024 * 1024 * 1024
    UPLOAD_RESERVATION_TTL_SECONDS: int = 15 * 60
    UPLOAD_QUOTA_RETRY_AFTER_SECONDS: int = 60
    EXPORT_USER_RATE_LIMIT_REQUESTS: int = 10
    EXPORT_ORGANIZATION_RATE_LIMIT_REQUESTS: int = 60
    EXPORT_RATE_LIMIT_WINDOW_SECONDS: int = 60
    EXPORT_MAX_CONCURRENT_PER_USER: int = 1
    EXPORT_MAX_CONCURRENT_PER_ORGANIZATION: int = 3
    EXPORT_TIMEOUT_SECONDS: int = 45
    EXPORT_QUEUE_BACKEND: Literal["memory", "redis"] = "memory"
    EXPORT_JOB_RETENTION_SECONDS: int = 24 * 60 * 60
    EXPORT_WORKER_LEASE_SECONDS: int = 75
    EXPORT_WORKER_HARD_TIMEOUT_SECONDS: int = 45
    EXPORT_WORKER_QUEUE_TIMEOUT_SECONDS: int = 5
    EXPORT_WORKER_REQUEUE_DELAY_SECONDS: int = 1
    EXPORT_WORKER_HEARTBEAT_INTERVAL_SECONDS: int = 15
    EXPORT_WORKER_HEARTBEAT_TTL_SECONDS: int = 90

    MFA_TOTP_ENCRYPTION_KEY: str = _DEV_MFA_FERNET_KEY
    MFA_RECOVERY_CODE_PEPPER: str = _DEV_MFA_RECOVERY_PEPPER
    MFA_CHALLENGE_EXPIRE_MINUTES: int = 5
    MFA_MAX_ATTEMPTS: int = 5
    MFA_RATE_LIMIT_ATTEMPTS: int = 5
    MFA_RATE_LIMIT_WINDOW_SECONDS: int = 10 * 60
    MFA_BREAK_GLASS_KEY_A_HASH: str | None = None
    MFA_BREAK_GLASS_KEY_B_HASH: str | None = None

    # Audit request/IP values are HMAC fingerprints rather than raw values.
    # Production must supply an independent secret so correlation survives
    # process restarts without storing the original identifiers.
    AUDIT_HASH_PEPPER: str = _DEV_AUDIT_HASH_PEPPER
    AUDIT_RETENTION_DAYS: int = 365
    AUDIT_CLEANUP_INTERVAL_SECONDS: int = 6 * 60 * 60

    LOG_LEVEL: str = "INFO"
    # Opt-in external error tracking. The event scrubber removes request,
    # user, breadcrumbs, custom extras, exception messages and stack traces.
    SENTRY_DSN: str | None = None
    SENTRY_ENVIRONMENT: str | None = None

    STORAGE_BACKEND: Literal["local", "s3"] = "local"
    STORAGE_LOCAL_PATH: str = "/app/storage_data"
    # S3 is deliberately opt-in. Development/test keep the local backend,
    # while production must make the S3 choice and every credential explicit.
    S3_ENDPOINT_URL: str | None = None
    S3_BUCKET: str | None = None
    S3_REGION: str | None = None
    S3_ACCESS_KEY_ID: str | None = None
    S3_SECRET_ACCESS_KEY: str | None = None
    S3_ADDRESSING_STYLE: Literal["auto", "path", "virtual"] = "auto"
    S3_VERIFY_TLS: bool = True
    FRONTEND_URL: str = "http://localhost:5173"
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM: str = "no-reply@practiceflow.local"

    @property
    def is_production(self) -> bool:
        return self.ENV.strip().lower() == "production"

    @property
    def trusted_proxy_networks(self) -> tuple[TrustedProxyNetwork, ...]:
        return parse_trusted_proxy_ips(self.TRUSTED_PROXY_IPS)

    @model_validator(mode="after")
    def validate_environment_safety(self) -> "Settings":
        trusted_proxy_networks = self.trusted_proxy_networks
        if self.STORAGE_BACKEND == "s3":
            required_s3_fields = (
                "S3_ENDPOINT_URL",
                "S3_BUCKET",
                "S3_REGION",
                "S3_ACCESS_KEY_ID",
                "S3_SECRET_ACCESS_KEY",
            )
            missing_s3_fields = [field for field in required_s3_fields if not (getattr(self, field) or "").strip()]
            if missing_s3_fields:
                raise ValueError("S3 storage requires explicit configuration: " + ", ".join(missing_s3_fields))
            endpoint = urlparse(self.S3_ENDPOINT_URL or "")
            if endpoint.scheme not in {"http", "https"} or not endpoint.netloc:
                raise ValueError("S3_ENDPOINT_URL must be an absolute http(s) URL")
        if not self.is_production:
            return self

        secret = self.JWT_SECRET_KEY.strip()
        if len(secret.encode("utf-8")) < 32 or secret.lower() in _PLACEHOLDER_SECRETS:
            raise ValueError(
                "JWT_SECRET_KEY must be a non-placeholder secret of at least 32 bytes in production"
            )
        if self.DATABASE_URL == _DEV_DATABASE_URL or not self.DATABASE_URL.strip():
            raise ValueError("DATABASE_URL must be explicitly configured in production")
        database_pool_fields = (
            "DATABASE_POOL_SIZE",
            "DATABASE_MAX_OVERFLOW",
            "DATABASE_POOL_TIMEOUT_SECONDS",
            "DATABASE_POOL_RECYCLE_SECONDS",
            "WORKER_DATABASE_POOL_SIZE",
            "WORKER_DATABASE_MAX_OVERFLOW",
            "WORKER_DATABASE_POOL_TIMEOUT_SECONDS",
            "WORKER_DATABASE_POOL_RECYCLE_SECONDS",
        )
        if self.DATABASE_POOL_SIZE <= 0 or self.WORKER_DATABASE_POOL_SIZE <= 0:
            raise ValueError("Database pool sizes must be positive")
        if self.DATABASE_MAX_OVERFLOW < 0 or self.WORKER_DATABASE_MAX_OVERFLOW < 0:
            raise ValueError("Database pool overflow values cannot be negative")
        if any(getattr(self, field) <= 0 for field in ("DATABASE_POOL_TIMEOUT_SECONDS", "DATABASE_POOL_RECYCLE_SECONDS", "WORKER_DATABASE_POOL_TIMEOUT_SECONDS", "WORKER_DATABASE_POOL_RECYCLE_SECONDS")):
            raise ValueError("Database pool timeout and recycle values must be positive")
        missing_database_pool_fields = [field for field in database_pool_fields if field not in self.model_fields_set]
        if missing_database_pool_fields:
            raise ValueError("Production requires explicit database pool settings: " + ", ".join(missing_database_pool_fields))
        if self.SEED_ON_START:
            raise ValueError("SEED_ON_START must be false in production")
        if not self.COOKIE_SECURE:
            raise ValueError("COOKIE_SECURE must be true in production")
        if self.LOGIN_RATE_LIMIT_BACKEND != "redis" or not self.REDIS_URL:
            raise ValueError("Production requires LOGIN_RATE_LIMIT_BACKEND=redis and REDIS_URL")
        if self.RESOURCE_GUARD_BACKEND != "redis" or not self.REDIS_URL:
            raise ValueError("Production requires RESOURCE_GUARD_BACKEND=redis and REDIS_URL")
        if self.EXPORT_QUEUE_BACKEND != "redis" or not self.REDIS_URL:
            raise ValueError("Production requires EXPORT_QUEUE_BACKEND=redis and REDIS_URL")
        if self.STORAGE_BACKEND != "s3":
            raise ValueError("Production requires STORAGE_BACKEND=s3; LocalStorage is development/test only")
        if not self.S3_VERIFY_TLS or not (self.S3_ENDPOINT_URL or "").startswith("https://"):
            raise ValueError("Production S3 storage requires an HTTPS endpoint with S3_VERIFY_TLS=true")
        if "*" in self.CORS_ORIGINS:
            raise ValueError("Wildcard CORS origins are not allowed in production")
        if not trusted_proxy_networks:
            raise ValueError("Production requires TRUSTED_PROXY_IPS with the explicit proxy IPs/CIDRs")
        if self.MFA_TOTP_ENCRYPTION_KEY == _DEV_MFA_FERNET_KEY:
            raise ValueError("MFA_TOTP_ENCRYPTION_KEY must be replaced in production")
        try:
            Fernet(self.MFA_TOTP_ENCRYPTION_KEY.encode("ascii"))
        except (ValueError, UnicodeEncodeError) as exc:
            raise ValueError("MFA_TOTP_ENCRYPTION_KEY must be a valid Fernet key") from exc
        if len(self.MFA_RECOVERY_CODE_PEPPER.encode("utf-8")) < 32 or self.MFA_RECOVERY_CODE_PEPPER == _DEV_MFA_RECOVERY_PEPPER:
            raise ValueError("MFA_RECOVERY_CODE_PEPPER must be a non-default secret in production")
        if len(self.AUDIT_HASH_PEPPER.encode("utf-8")) < 32 or self.AUDIT_HASH_PEPPER == _DEV_AUDIT_HASH_PEPPER:
            raise ValueError("AUDIT_HASH_PEPPER must be a non-default secret in production")
        if self.AUDIT_RETENTION_DAYS <= 0 or self.AUDIT_CLEANUP_INTERVAL_SECONDS <= 0:
            raise ValueError("Audit retention and cleanup interval values must be positive")
        if not self.MFA_BREAK_GLASS_KEY_A_HASH or not self.MFA_BREAK_GLASS_KEY_B_HASH:
            raise ValueError("Production requires both MFA break-glass custodian key hashes")
        for value in (self.MFA_BREAK_GLASS_KEY_A_HASH, self.MFA_BREAK_GLASS_KEY_B_HASH):
            if len(value) != 64 or any(char not in "0123456789abcdefABCDEF" for char in value):
                raise ValueError("MFA break-glass custodian hashes must be SHA-256 hex values")
        if self.MFA_CHALLENGE_EXPIRE_MINUTES <= 0 or self.MFA_MAX_ATTEMPTS <= 0 or self.MFA_RATE_LIMIT_ATTEMPTS <= 0 or self.MFA_RATE_LIMIT_WINDOW_SECONDS <= 0:
            raise ValueError("MFA expiry and rate-limit values must be positive")
        resource_limit_fields = (
            "UPLOAD_MAX_FILE_BYTES",
            "UPLOAD_RATE_LIMIT_REQUESTS",
            "UPLOAD_RATE_LIMIT_WINDOW_SECONDS",
            "UPLOAD_USER_MAX_FILES",
            "UPLOAD_USER_MAX_BYTES",
            "UPLOAD_USER_QUOTA_WINDOW_SECONDS",
            "UPLOAD_ORGANIZATION_MAX_STORAGE_BYTES",
            "UPLOAD_RESERVATION_TTL_SECONDS",
            "UPLOAD_QUOTA_RETRY_AFTER_SECONDS",
            "EXPORT_USER_RATE_LIMIT_REQUESTS",
            "EXPORT_ORGANIZATION_RATE_LIMIT_REQUESTS",
            "EXPORT_RATE_LIMIT_WINDOW_SECONDS",
            "EXPORT_MAX_CONCURRENT_PER_USER",
            "EXPORT_MAX_CONCURRENT_PER_ORGANIZATION",
            "EXPORT_TIMEOUT_SECONDS",
            "EXPORT_JOB_RETENTION_SECONDS",
            "EXPORT_WORKER_LEASE_SECONDS",
            "EXPORT_WORKER_HARD_TIMEOUT_SECONDS",
            "EXPORT_WORKER_QUEUE_TIMEOUT_SECONDS",
            "EXPORT_WORKER_REQUEUE_DELAY_SECONDS",
            "EXPORT_WORKER_HEARTBEAT_INTERVAL_SECONDS",
            "EXPORT_WORKER_HEARTBEAT_TTL_SECONDS",
            "DOCUMENT_CHECK_WORKER_POLL_SECONDS",
            "DOCUMENT_CHECK_WORKER_TIMEOUT_SECONDS",
            "DOCUMENT_CHECK_WORKER_LEASE_SECONDS",
            "DOCUMENT_CHECK_WORKER_MAX_ATTEMPTS",
            "DOCUMENT_CHECK_MAX_FINDINGS",
            "LOCAL_PLAGIARISM_MIN_MATCH_WORDS",
            "LOCAL_PLAGIARISM_MAX_MATCHES",
            "LOCAL_PLAGIARISM_MAX_CANDIDATE_DOCUMENTS",
            "LOCAL_PLAGIARISM_MAX_INDEXED_WORDS",
        )
        if any(getattr(self, field) <= 0 for field in resource_limit_fields):
            raise ValueError("Upload and export resource-protection values must be positive")
        # Defaults are deliberately convenient for development, but a
        # deployment must choose and review every resource limit explicitly.
        missing_resource_limits = [field for field in resource_limit_fields if field not in self.model_fields_set]
        if missing_resource_limits:
            raise ValueError(
                "Production requires explicit upload/export resource-protection settings: "
                + ", ".join(missing_resource_limits)
            )
        audit_fields = ("AUDIT_RETENTION_DAYS", "AUDIT_CLEANUP_INTERVAL_SECONDS")
        missing_audit_fields = [field for field in audit_fields if field not in self.model_fields_set]
        if missing_audit_fields:
            raise ValueError("Production requires explicit audit retention settings: " + ", ".join(missing_audit_fields))
        if self.EXPORT_WORKER_HARD_TIMEOUT_SECONDS > self.EXPORT_WORKER_LEASE_SECONDS:
            raise ValueError("EXPORT_WORKER_LEASE_SECONDS must be at least EXPORT_WORKER_HARD_TIMEOUT_SECONDS")
        if self.EXPORT_WORKER_HEARTBEAT_INTERVAL_SECONDS >= self.EXPORT_WORKER_HEARTBEAT_TTL_SECONDS:
            raise ValueError("EXPORT_WORKER_HEARTBEAT_INTERVAL_SECONDS must be shorter than its TTL")
        if self.DOCUMENT_CHECK_WORKER_TIMEOUT_SECONDS >= self.DOCUMENT_CHECK_WORKER_LEASE_SECONDS:
            raise ValueError("DOCUMENT_CHECK_WORKER_LEASE_SECONDS must exceed the analyzer timeout")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
