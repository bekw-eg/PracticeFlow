from functools import lru_cache

from app.core.config import settings
from app.rate_limit.base import LoginRateLimiter
from app.rate_limit.memory import MemoryLoginRateLimiter
from app.rate_limit.redis_backend import RedisLoginRateLimiter
from app.resource_protection import MemoryResourceGuard, RedisResourceGuard, ResourceGuard, ResourceProtectionConfig
from app.export_queue import ExportQueue, MemoryExportQueue, RedisExportQueue


@lru_cache
def get_login_rate_limiter() -> LoginRateLimiter:
    if settings.LOGIN_RATE_LIMIT_BACKEND == "redis":
        if not settings.REDIS_URL:
            raise RuntimeError("REDIS_URL is required for the Redis rate-limit backend")
        return RedisLoginRateLimiter(
            settings.REDIS_URL,
            settings.LOGIN_RATE_LIMIT_ATTEMPTS,
            settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS,
        )
    return MemoryLoginRateLimiter(
        settings.LOGIN_RATE_LIMIT_ATTEMPTS,
        settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS,
    )


@lru_cache
def get_mfa_rate_limiter() -> LoginRateLimiter:
    """Separate rate-limit bucket so MFA guesses never affect password login."""
    if settings.LOGIN_RATE_LIMIT_BACKEND == "redis":
        if not settings.REDIS_URL:
            raise RuntimeError("REDIS_URL is required for the Redis rate-limit backend")
        return RedisLoginRateLimiter(
            settings.REDIS_URL,
            settings.MFA_RATE_LIMIT_ATTEMPTS,
            settings.MFA_RATE_LIMIT_WINDOW_SECONDS,
            key_namespace="mfa-failures",
        )
    return MemoryLoginRateLimiter(settings.MFA_RATE_LIMIT_ATTEMPTS, settings.MFA_RATE_LIMIT_WINDOW_SECONDS)


@lru_cache
def get_resource_guard() -> ResourceGuard:
    config = ResourceProtectionConfig.from_settings(settings)
    if settings.RESOURCE_GUARD_BACKEND == "redis":
        if not settings.REDIS_URL:
            raise RuntimeError("REDIS_URL is required for the Redis resource-protection backend")
        return RedisResourceGuard(settings.REDIS_URL, config)
    return MemoryResourceGuard(config)


@lru_cache
def get_export_queue() -> ExportQueue:
    if settings.EXPORT_QUEUE_BACKEND == "redis":
        if not settings.REDIS_URL:
            raise RuntimeError("REDIS_URL is required for the Redis export queue")
        return RedisExportQueue(settings.REDIS_URL)
    return MemoryExportQueue()
