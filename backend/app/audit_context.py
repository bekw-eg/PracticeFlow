"""Request-scoped, privacy-preserving correlation for audit entries."""
from __future__ import annotations

import hashlib
import hmac
from contextvars import ContextVar, Token
from dataclasses import dataclass

from app.core.config import settings


@dataclass(frozen=True)
class AuditRequestContext:
    request_id_hash: str | None = None
    source_ip_hash: str | None = None
    correlation_id_hash: str | None = None


_context: ContextVar[AuditRequestContext] = ContextVar("audit_request_context", default=AuditRequestContext())


def fingerprint(value: str | None) -> str | None:
    """Return a stable keyed fingerprint; never persist raw request/IP data."""
    if not value:
        return None
    return hmac.new(settings.AUDIT_HASH_PEPPER.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()


def set_request_audit_context(request_id: str | None, source_ip: str | None) -> Token[AuditRequestContext]:
    return _context.set(AuditRequestContext(request_id_hash=fingerprint(request_id), source_ip_hash=fingerprint(source_ip)))


def reset_request_audit_context(token: Token[AuditRequestContext]) -> None:
    _context.reset(token)


def get_audit_context() -> AuditRequestContext:
    return _context.get()
