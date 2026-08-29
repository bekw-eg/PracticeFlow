"""Shared, tenant-scoped protection against costly uploads and exports.

The durable storage total remains the ``files`` table.  Redis only tracks
short-lived upload reservations while a file is being persisted, plus request
windows and export slots.  Consequently an expired Redis key can fail closed
for a short time, but can never expose or attribute another organization's
files to the current organization.
"""
from __future__ import annotations

import math
import threading
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass

import redis
from fastapi import HTTPException, status

from app.core.config import Settings, settings
from app.observability.metrics import metrics


@dataclass(frozen=True)
class ResourceProtectionConfig:
    upload_rate_requests: int
    upload_rate_window_seconds: int
    upload_user_max_files: int
    upload_user_max_bytes: int
    upload_user_quota_window_seconds: int
    upload_org_max_storage_bytes: int
    upload_reservation_ttl_seconds: int
    upload_quota_retry_after_seconds: int
    export_user_rate_requests: int
    export_org_rate_requests: int
    export_rate_window_seconds: int
    export_max_concurrent_per_user: int
    export_max_concurrent_per_org: int
    export_timeout_seconds: int

    @classmethod
    def from_settings(cls, value: Settings = settings) -> "ResourceProtectionConfig":
        return cls(
            upload_rate_requests=value.UPLOAD_RATE_LIMIT_REQUESTS,
            upload_rate_window_seconds=value.UPLOAD_RATE_LIMIT_WINDOW_SECONDS,
            upload_user_max_files=value.UPLOAD_USER_MAX_FILES,
            upload_user_max_bytes=value.UPLOAD_USER_MAX_BYTES,
            upload_user_quota_window_seconds=value.UPLOAD_USER_QUOTA_WINDOW_SECONDS,
            upload_org_max_storage_bytes=value.UPLOAD_ORGANIZATION_MAX_STORAGE_BYTES,
            upload_reservation_ttl_seconds=value.UPLOAD_RESERVATION_TTL_SECONDS,
            upload_quota_retry_after_seconds=value.UPLOAD_QUOTA_RETRY_AFTER_SECONDS,
            export_user_rate_requests=value.EXPORT_USER_RATE_LIMIT_REQUESTS,
            export_org_rate_requests=value.EXPORT_ORGANIZATION_RATE_LIMIT_REQUESTS,
            export_rate_window_seconds=value.EXPORT_RATE_LIMIT_WINDOW_SECONDS,
            export_max_concurrent_per_user=value.EXPORT_MAX_CONCURRENT_PER_USER,
            export_max_concurrent_per_org=value.EXPORT_MAX_CONCURRENT_PER_ORGANIZATION,
            export_timeout_seconds=value.EXPORT_TIMEOUT_SECONDS,
        )


@dataclass(frozen=True)
class UploadReservation:
    organization_id: str
    reservation_id: str


@dataclass(frozen=True)
class ExportLease:
    organization_id: str
    user_id: str


def _limit_error(detail: str, retry_after: int, reason: str) -> HTTPException:
    metrics.observe_limit_block(reason)
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=detail,
        headers={"Retry-After": str(max(1, retry_after))},
    )


def _unavailable_error() -> HTTPException:
    metrics.observe_dependency("redis_resource_guard", "failure")
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Resource protection is temporarily unavailable. Please retry shortly.",
    )


class ResourceGuard(ABC):
    """Atomic resource limiter. All identifiers must already be tenant scoped."""

    config: ResourceProtectionConfig

    @abstractmethod
    def check_upload_request(self, organization_id: uuid.UUID, user_id: uuid.UUID) -> None:
        ...

    @abstractmethod
    def reserve_upload(
        self, organization_id: uuid.UUID, user_id: uuid.UUID, file_size: int, organization_storage_bytes: int
    ) -> UploadReservation:
        ...

    @abstractmethod
    def complete_upload(self, reservation: UploadReservation) -> None:
        ...

    @abstractmethod
    def cancel_upload(self, reservation: UploadReservation) -> None:
        ...

    @abstractmethod
    def check_export_rate(self, organization_id: uuid.UUID, user_id: uuid.UUID) -> None:
        """Consume a user/org export request allowance at job creation."""
        ...

    @abstractmethod
    def acquire_export_slot(self, organization_id: uuid.UUID, user_id: uuid.UUID) -> ExportLease:
        """Acquire rendering capacity in a worker, not in an HTTP request."""
        ...

    @abstractmethod
    def release_export(self, lease: ExportLease) -> None:
        ...

    def acquire_export(self, organization_id: uuid.UUID, user_id: uuid.UUID) -> ExportLease:
        """Backward-compatible combined operation for callers outside jobs."""
        self.check_export_rate(organization_id, user_id)
        return self.acquire_export_slot(organization_id, user_id)

    def ping(self) -> bool:
        return True


@dataclass
class _Window:
    started_at: float
    count: int = 0
    bytes_used: int = 0


class MemoryResourceGuard(ResourceGuard):
    """Thread-safe development/test guard with the same atomic semantics.

    It intentionally is not shared between processes; Settings rejects it in
    production where more than one API replica may exist.
    """

    def __init__(self, config: ResourceProtectionConfig):
        self.config = config
        self._lock = threading.Lock()
        self._upload_requests: dict[tuple[str, str], _Window] = {}
        self._upload_quotas: dict[tuple[str, str], _Window] = {}
        self._upload_reservations: dict[str, dict[str, tuple[int, float]]] = {}
        self._export_rates_user: dict[tuple[str, str], _Window] = {}
        self._export_rates_org: dict[str, _Window] = {}
        self._export_slots_user: dict[tuple[str, str], tuple[int, float]] = {}
        self._export_slots_org: dict[str, tuple[int, float]] = {}

    @staticmethod
    def _fresh_window(store: dict, key, seconds: int, now: float) -> _Window:
        value = store.get(key)
        if value is None or now - value.started_at >= seconds:
            value = _Window(started_at=now)
            store[key] = value
        return value

    @staticmethod
    def _remaining(window: _Window, seconds: int, now: float) -> int:
        return max(1, math.ceil(seconds - (now - window.started_at)))

    def _cleanup_reservations(self, organization_id: str, now: float) -> None:
        reservations = self._upload_reservations.get(organization_id, {})
        for reservation_id, (_size, expires_at) in list(reservations.items()):
            if expires_at <= now:
                reservations.pop(reservation_id, None)

    @staticmethod
    def _active_slots(value: tuple[int, float] | None, now: float) -> int:
        if value is None or value[1] <= now:
            return 0
        return value[0]

    def check_upload_request(self, organization_id: uuid.UUID, user_id: uuid.UUID) -> None:
        now = time.monotonic()
        key = (str(organization_id), str(user_id))
        with self._lock:
            window = self._fresh_window(self._upload_requests, key, self.config.upload_rate_window_seconds, now)
            if window.count >= self.config.upload_rate_requests:
                raise _limit_error("Upload rate limit exceeded.", self._remaining(window, self.config.upload_rate_window_seconds, now), "upload_rate")
            window.count += 1

    def reserve_upload(
        self, organization_id: uuid.UUID, user_id: uuid.UUID, file_size: int, organization_storage_bytes: int
    ) -> UploadReservation:
        now = time.monotonic()
        org_key, user_key = str(organization_id), str(user_id)
        with self._lock:
            quota = self._fresh_window(
                self._upload_quotas, (org_key, user_key), self.config.upload_user_quota_window_seconds, now
            )
            if quota.count + 1 > self.config.upload_user_max_files or quota.bytes_used + file_size > self.config.upload_user_max_bytes:
                raise _limit_error(
                    "Upload user quota exceeded.", self._remaining(quota, self.config.upload_user_quota_window_seconds, now), "upload_quota"
                )
            self._cleanup_reservations(org_key, now)
            pending = sum(size for size, _expires_at in self._upload_reservations.get(org_key, {}).values())
            if organization_storage_bytes + pending + file_size > self.config.upload_org_max_storage_bytes:
                raise _limit_error("Organization storage quota exceeded.", self.config.upload_quota_retry_after_seconds, "upload_quota")
            reservation_id = str(uuid.uuid4())
            self._upload_reservations.setdefault(org_key, {})[reservation_id] = (
                file_size,
                now + self.config.upload_reservation_ttl_seconds,
            )
            quota.count += 1
            quota.bytes_used += file_size
            return UploadReservation(org_key, reservation_id)

    def _release_upload_reservation(self, reservation: UploadReservation) -> None:
        with self._lock:
            reservations = self._upload_reservations.get(reservation.organization_id)
            if reservations is not None:
                reservations.pop(reservation.reservation_id, None)

    def complete_upload(self, reservation: UploadReservation) -> None:
        self._release_upload_reservation(reservation)

    def cancel_upload(self, reservation: UploadReservation) -> None:
        # A failed persistence still consumes a user-period allowance. This
        # prevents retrying a deliberately expensive valid image until a local
        # storage failure becomes an upload-rate bypass.
        self._release_upload_reservation(reservation)

    def check_export_rate(self, organization_id: uuid.UUID, user_id: uuid.UUID) -> None:
        now = time.monotonic()
        org_key, user_key = str(organization_id), str(user_id)
        with self._lock:
            user_rate = self._fresh_window(
                self._export_rates_user, (org_key, user_key), self.config.export_rate_window_seconds, now
            )
            org_rate = self._fresh_window(self._export_rates_org, org_key, self.config.export_rate_window_seconds, now)
            if user_rate.count >= self.config.export_user_rate_requests or org_rate.count >= self.config.export_org_rate_requests:
                retry_after = max(
                    self._remaining(user_rate, self.config.export_rate_window_seconds, now),
                    self._remaining(org_rate, self.config.export_rate_window_seconds, now),
                )
                raise _limit_error("Export rate limit exceeded.", retry_after, "export_rate")

            user_rate.count += 1
            org_rate.count += 1

    def acquire_export_slot(self, organization_id: uuid.UUID, user_id: uuid.UUID) -> ExportLease:
        now = time.monotonic()
        org_key, user_key = str(organization_id), str(user_id)
        with self._lock:
            user_slot_key = (org_key, user_key)
            user_slots = self._active_slots(self._export_slots_user.get(user_slot_key), now)
            org_slots = self._active_slots(self._export_slots_org.get(org_key), now)
            if user_slots >= self.config.export_max_concurrent_per_user or org_slots >= self.config.export_max_concurrent_per_org:
                raise _limit_error("Export concurrency limit exceeded.", self.config.export_timeout_seconds, "export_concurrency")

            expires_at = now + self.config.export_timeout_seconds
            self._export_slots_user[user_slot_key] = (user_slots + 1, expires_at)
            self._export_slots_org[org_key] = (org_slots + 1, expires_at)
            return ExportLease(org_key, user_key)

    def release_export(self, lease: ExportLease) -> None:
        now = time.monotonic()
        with self._lock:
            user_key = (lease.organization_id, lease.user_id)
            user_slots = self._active_slots(self._export_slots_user.get(user_key), now)
            org_slots = self._active_slots(self._export_slots_org.get(lease.organization_id), now)
            if user_slots:
                self._export_slots_user[user_key] = (user_slots - 1, now + self.config.export_timeout_seconds)
            if org_slots:
                self._export_slots_org[lease.organization_id] = (org_slots - 1, now + self.config.export_timeout_seconds)


_UPLOAD_RATE_SCRIPT = """
local current = tonumber(redis.call('GET', KEYS[1]) or '0')
if current >= tonumber(ARGV[1]) then
  return {0, math.max(1, math.ceil((redis.call('PTTL', KEYS[1]) or 1000) / 1000))}
end
current = redis.call('INCR', KEYS[1])
if current == 1 then redis.call('EXPIRE', KEYS[1], tonumber(ARGV[2])) end
return {1, 0}
"""

_RESERVE_UPLOAD_SCRIPT = """
local time = redis.call('TIME')
local now = tonumber(time[1])
local stale = redis.call('ZRANGEBYSCORE', KEYS[3], '-inf', now)
for _, reservation_id in ipairs(stale) do
  local bytes = tonumber(redis.call('HGET', KEYS[2], reservation_id) or '0')
  if bytes > 0 then redis.call('HINCRBY', KEYS[2], '__total__', -bytes) end
  redis.call('HDEL', KEYS[2], reservation_id)
  redis.call('ZREM', KEYS[3], reservation_id)
end
local file_count = tonumber(redis.call('HGET', KEYS[1], 'count') or '0')
local byte_count = tonumber(redis.call('HGET', KEYS[1], 'bytes') or '0')
local quota_ttl = redis.call('TTL', KEYS[1])
if file_count + 1 > tonumber(ARGV[1]) or byte_count + tonumber(ARGV[2]) > tonumber(ARGV[3]) then
  return {0, math.max(1, quota_ttl)}
end
local reserved = tonumber(redis.call('HGET', KEYS[2], '__total__') or '0')
if tonumber(ARGV[4]) + reserved + tonumber(ARGV[2]) > tonumber(ARGV[5]) then
  return {0, tonumber(ARGV[7])}
end
redis.call('HSET', KEYS[1], 'count', file_count + 1, 'bytes', byte_count + tonumber(ARGV[2]))
if quota_ttl < 0 then redis.call('EXPIRE', KEYS[1], tonumber(ARGV[6])) end
redis.call('HSET', KEYS[2], ARGV[8], ARGV[2])
redis.call('HINCRBY', KEYS[2], '__total__', tonumber(ARGV[2]))
redis.call('ZADD', KEYS[3], now + tonumber(ARGV[9]), ARGV[8])
redis.call('EXPIRE', KEYS[2], tonumber(ARGV[9]))
redis.call('EXPIRE', KEYS[3], tonumber(ARGV[9]))
return {1, 0}
"""

_RELEASE_UPLOAD_SCRIPT = """
local bytes = tonumber(redis.call('HGET', KEYS[1], ARGV[1]) or '0')
if bytes > 0 then redis.call('HINCRBY', KEYS[1], '__total__', -bytes) end
redis.call('HDEL', KEYS[1], ARGV[1])
redis.call('ZREM', KEYS[2], ARGV[1])
if tonumber(redis.call('HGET', KEYS[1], '__total__') or '0') <= 0 then
  redis.call('DEL', KEYS[1])
  redis.call('DEL', KEYS[2])
end
return 1
"""

_CHECK_EXPORT_RATE_SCRIPT = """
local function rate_allowed(key, limit)
  return tonumber(redis.call('GET', key) or '0') < tonumber(limit)
end
if not rate_allowed(KEYS[1], ARGV[1]) or not rate_allowed(KEYS[2], ARGV[2]) then
  local user_ttl = redis.call('PTTL', KEYS[1]) or 0
  local org_ttl = redis.call('PTTL', KEYS[2]) or 0
  return {0, math.max(1, math.ceil(math.max(user_ttl, org_ttl) / 1000))}
end
local user_rate = redis.call('INCR', KEYS[1])
if user_rate == 1 then redis.call('EXPIRE', KEYS[1], tonumber(ARGV[3])) end
local org_rate = redis.call('INCR', KEYS[2])
if org_rate == 1 then redis.call('EXPIRE', KEYS[2], tonumber(ARGV[3])) end
return {1, 0}
"""

_ACQUIRE_EXPORT_SLOT_SCRIPT = """
local user_slots = tonumber(redis.call('GET', KEYS[1]) or '0')
local org_slots = tonumber(redis.call('GET', KEYS[2]) or '0')
if user_slots >= tonumber(ARGV[1]) or org_slots >= tonumber(ARGV[2]) then
  return {0, tonumber(ARGV[3])}
end
local user_slot_count = redis.call('INCR', KEYS[1])
if user_slot_count == 1 then redis.call('EXPIRE', KEYS[1], tonumber(ARGV[3])) end
local org_slot_count = redis.call('INCR', KEYS[2])
if org_slot_count == 1 then redis.call('EXPIRE', KEYS[2], tonumber(ARGV[3])) end
return {1, 0}
"""

_RELEASE_EXPORT_SCRIPT = """
for _, key in ipairs(KEYS) do
  local current = tonumber(redis.call('GET', key) or '0')
  if current <= 1 then redis.call('DEL', key) else redis.call('DECR', key) end
end
return 1
"""


class RedisResourceGuard(ResourceGuard):
    """Redis-backed guard. Redis errors fail closed; they never bypass a limit."""

    def __init__(self, url: str, config: ResourceProtectionConfig):
        self.client = redis.Redis.from_url(url, decode_responses=True, socket_timeout=2)
        self.config = config

    @staticmethod
    def _key(*parts: str) -> str:
        return "practiceflow:resource:" + ":".join(parts)

    def _eval(self, script: str, keys: list[str], args: list[str | int]):
        try:
            result = self.client.eval(script, len(keys), *keys, *(str(arg) for arg in args))
        except redis.RedisError as exc:
            raise _unavailable_error() from exc
        metrics.observe_dependency("redis_resource_guard", "success")
        return result

    def check_upload_request(self, organization_id: uuid.UUID, user_id: uuid.UUID) -> None:
        result = self._eval(
            _UPLOAD_RATE_SCRIPT,
            [self._key("upload-rate", str(organization_id), str(user_id))],
            [self.config.upload_rate_requests, self.config.upload_rate_window_seconds],
        )
        if int(result[0]) == 0:
            raise _limit_error("Upload rate limit exceeded.", int(result[1]), "upload_rate")

    def reserve_upload(
        self, organization_id: uuid.UUID, user_id: uuid.UUID, file_size: int, organization_storage_bytes: int
    ) -> UploadReservation:
        org_key, user_key, reservation_id = str(organization_id), str(user_id), str(uuid.uuid4())
        result = self._eval(
            _RESERVE_UPLOAD_SCRIPT,
            [
                self._key("upload-quota", org_key, user_key),
                self._key("upload-reservations", org_key),
                self._key("upload-reservation-expiry", org_key),
            ],
            [
                self.config.upload_user_max_files,
                file_size,
                self.config.upload_user_max_bytes,
                organization_storage_bytes,
                self.config.upload_org_max_storage_bytes,
                self.config.upload_user_quota_window_seconds,
                self.config.upload_quota_retry_after_seconds,
                reservation_id,
                self.config.upload_reservation_ttl_seconds,
            ],
        )
        if int(result[0]) == 0:
            raise _limit_error("Upload quota exceeded.", int(result[1]), "upload_quota")
        return UploadReservation(org_key, reservation_id)

    def _release_upload(self, reservation: UploadReservation) -> None:
        self._eval(
            _RELEASE_UPLOAD_SCRIPT,
            [
                self._key("upload-reservations", reservation.organization_id),
                self._key("upload-reservation-expiry", reservation.organization_id),
            ],
            [reservation.reservation_id],
        )

    def complete_upload(self, reservation: UploadReservation) -> None:
        self._release_upload(reservation)

    def cancel_upload(self, reservation: UploadReservation) -> None:
        self._release_upload(reservation)

    def check_export_rate(self, organization_id: uuid.UUID, user_id: uuid.UUID) -> None:
        org_key, user_key = str(organization_id), str(user_id)
        result = self._eval(
            _CHECK_EXPORT_RATE_SCRIPT,
            [
                self._key("export-rate-user", org_key, user_key),
                self._key("export-rate-org", org_key),
            ],
            [
                self.config.export_user_rate_requests,
                self.config.export_org_rate_requests,
                self.config.export_rate_window_seconds,
            ],
        )
        if int(result[0]) == 0:
            raise _limit_error("Export rate limit exceeded.", int(result[1]), "export_rate")

    def acquire_export_slot(self, organization_id: uuid.UUID, user_id: uuid.UUID) -> ExportLease:
        org_key, user_key = str(organization_id), str(user_id)
        result = self._eval(
            _ACQUIRE_EXPORT_SLOT_SCRIPT,
            [
                self._key("export-slot-user", org_key, user_key),
                self._key("export-slot-org", org_key),
            ],
            [
                self.config.export_max_concurrent_per_user,
                self.config.export_max_concurrent_per_org,
                self.config.export_timeout_seconds,
            ],
        )
        if int(result[0]) == 0:
            raise _limit_error("Export concurrency limit exceeded.", int(result[1]), "export_concurrency")
        return ExportLease(org_key, user_key)

    def release_export(self, lease: ExportLease) -> None:
        self._eval(
            _RELEASE_EXPORT_SCRIPT,
            [
                self._key("export-slot-user", lease.organization_id, lease.user_id),
                self._key("export-slot-org", lease.organization_id),
            ],
            [],
        )

    def ping(self) -> bool:
        try:
            available = bool(self.client.ping())
        except redis.RedisError:
            available = False
        metrics.observe_dependency("redis_resource_guard", "success" if available else "failure")
        return available
