from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
import redis
from fastapi import HTTPException

from app.core.config import settings
from app.resource_protection import MemoryResourceGuard, RedisResourceGuard, ResourceProtectionConfig
from app.tests.conftest import OrgFixture


def _guard(**changes) -> MemoryResourceGuard:
    defaults = ResourceProtectionConfig.from_settings(settings)
    return MemoryResourceGuard(replace(defaults, **changes))


def test_upload_request_rate_returns_429_with_retry_after(org_a: OrgFixture):
    guard = _guard(upload_rate_requests=1, upload_rate_window_seconds=60)

    guard.check_upload_request(org_a.org.id, org_a.teacher_user.id)
    with pytest.raises(HTTPException) as limited:
        guard.check_upload_request(org_a.org.id, org_a.teacher_user.id)

    assert limited.value.status_code == 429
    assert int(limited.value.headers["Retry-After"]) > 0


def test_concurrent_upload_reservations_cannot_overbook_organization_storage(org_a: OrgFixture):
    guard = _guard(upload_org_max_storage_bytes=100, upload_user_max_bytes=1000, upload_rate_requests=10)

    def reserve_once():
        try:
            return guard.reserve_upload(org_a.org.id, org_a.teacher_user.id, 60, 0)
        except HTTPException as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _index: reserve_once(), range(2)))

    successes = [outcome for outcome in outcomes if not isinstance(outcome, HTTPException)]
    failures = [outcome for outcome in outcomes if isinstance(outcome, HTTPException)]
    assert len(successes) == 1
    assert len(failures) == 1
    assert failures[0].status_code == 429


def test_export_slot_is_released_after_renderer_exception(org_a: OrgFixture):
    guard = _guard(export_max_concurrent_per_user=1, export_max_concurrent_per_org=1, export_user_rate_requests=10)

    lease = guard.acquire_export(org_a.org.id, org_a.teacher_user.id)
    try:
        raise RuntimeError("renderer failed")
    except RuntimeError:
        guard.release_export(lease)

    # A subsequent request can acquire the slot instead of being blocked by a
    # failed export from the same user/organization.
    replacement = guard.acquire_export(org_a.org.id, org_a.teacher_user.id)
    guard.release_export(replacement)


def test_redis_guard_fails_closed_when_redis_is_unavailable(org_a: OrgFixture):
    class UnavailableRedis:
        def eval(self, *_args, **_kwargs):
            raise redis.ConnectionError("redis is down")

        def ping(self):
            raise redis.ConnectionError("redis is down")

    guard = RedisResourceGuard("redis://unused", ResourceProtectionConfig.from_settings(settings))
    guard.client = UnavailableRedis()

    with pytest.raises(HTTPException) as unavailable:
        guard.check_upload_request(org_a.org.id, org_a.teacher_user.id)

    assert unavailable.value.status_code == 503
    assert guard.ping() is False
