import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import bcrypt
import jwt

from app.core.config import settings

TokenType = Literal["access", "refresh"]
MIN_PASSWORD_BYTES = 8
MAX_PASSWORD_BYTES = 72


def validate_password(password: str) -> str:
    """Validate the exact byte sequence bcrypt will receive.

    bcrypt ignores bytes after byte 72.  Silently truncating would make two
    visibly different passwords authenticate as the same secret, so this
    application deliberately rejects passwords outside the supported range.
    """
    length = len(password.encode("utf-8"))
    if length < MIN_PASSWORD_BYTES:
        raise ValueError(f"Password must contain at least {MIN_PASSWORD_BYTES} UTF-8 bytes")
    if length > MAX_PASSWORD_BYTES:
        raise ValueError(f"Password must not exceed {MAX_PASSWORD_BYTES} UTF-8 bytes")
    return password


def hash_password(password: str) -> str:
    validate_password(password)
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        validate_password(plain_password)
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def _create_token(subject: str, token_type: TokenType, expires_delta: timedelta, extra_claims: dict[str, Any] | None = None) -> tuple[str, str]:
    """Returns (encoded_jwt, jti)."""
    now = datetime.now(timezone.utc)
    jti = str(uuid.uuid4())
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
        "jti": jti,
    }
    if extra_claims:
        payload.update(extra_claims)
    encoded = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded, jti


def create_access_token(
    user_id: uuid.UUID,
    org_id: uuid.UUID | None,
    role: str | None,
    *,
    mfa_verified: bool = False,
    mfa_security_version: int | None = None,
) -> str:
    token, _ = _create_token(
        subject=str(user_id),
        token_type="access",
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        extra_claims={
            "org_id": str(org_id) if org_id else None,
            "role": role,
            "mfa_verified": mfa_verified,
            "mfa_security_version": mfa_security_version,
        },
    )
    return token


def create_refresh_token(
    user_id: uuid.UUID,
    organization_id: uuid.UUID,
    *,
    mfa_verified: bool = False,
    mfa_security_version: int | None = None,
) -> tuple[str, str, datetime]:
    """Returns (token, jti, expires_at) — caller persists jti server-side for revocation."""
    expires_delta = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    token, jti = _create_token(
        subject=str(user_id),
        token_type="refresh",
        expires_delta=expires_delta,
        extra_claims={
            "org_id": str(organization_id),
            "mfa_verified": mfa_verified,
            "mfa_security_version": mfa_security_version,
        },
    )
    expires_at = datetime.now(timezone.utc) + expires_delta
    return token, jti, expires_at


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
