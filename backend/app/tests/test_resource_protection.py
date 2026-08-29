import io
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
import redis
from fastapi import HTTPException
from PIL import Image

from app.core.config import settings
from app.rate_limit.dependencies import get_resource_guard
from app.resource_protection import MemoryResourceGuard, RedisResourceGuard, ResourceProtectionConfig
from app.services.export_execution import run_export_with_timeout
from app.tests.conftest import OrgFixture, auth_headers


def _png_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGBA", (1, 1), (0, 0, 0, 0)).save(output, format="PNG")
    return output.getvalue()


def _guard(**changes) -> MemoryResourceGuard:
    defaults = ResourceProtectionConfig.from_settings(settings)
    return MemoryResourceGuard(replace(defaults, **changes))


def _upload(client, token: str, payload: bytes | None = None):
    return client.post(
        "/api/v1/files",
        headers=auth_headers(token),
        files={"file": ("test.png", io.BytesIO(payload or _png_bytes()), "image/png")},
    )


def test_upload_enforces_configured_file_size_before_materializing_whole_file(client, org_a: OrgFixture, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_MAX_FILE_BYTES", 10)

    response = _upload(client, org_a.teacher_token(client))

    assert response.status_code == 413


def test_upload_user_quota_returns_429_with_retry_after(client, org_a: OrgFixture):
    image = _png_bytes()
    guard = _guard(upload_user_max_bytes=len(image) + 1, upload_rate_requests=10)
    from app.main import app

    app.dependency_overrides[get_resource_guard] = lambda: guard
    token = org_a.teacher_token(client)
    assert _upload(client, token, image).status_code == 201

    response = _upload(client, token, image)

    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) > 0


def test_upload_request_rate_returns_429_with_retry_after(org_a: OrgFixture):
    guard = _guard(upload_rate_requests=1, upload_rate_window_seconds=60)

    guard.check_upload_request(org_a.org.id, org_a.teacher_user.id)
    with pytest.raises(HTTPException) as limited:
        guard.check_upload_request(org_a.org.id, org_a.teacher_user.id)

    assert limited.value.status_code == 429
    assert int(limited.value.headers["Retry-After"]) > 0


def test_organization_quota_is_tenant_scoped(client, org_a: OrgFixture, org_b: OrgFixture):
    image = _png_bytes()
    guard = _guard(upload_org_max_storage_bytes=len(image) + 1, upload_rate_requests=10)
    from app.main import app

    app.dependency_overrides[get_resource_guard] = lambda: guard
    assert _upload(client, org_a.teacher_token(client), image).status_code == 201

    # A second member of the same organization cannot exceed its actual
    # persisted bytes, while a second organization starts from its own total.
    same_tenant = _upload(client, org_a.student_token(client), image)
    other_tenant = _upload(client, org_b.teacher_token(client), image)

    assert same_tenant.status_code == 429
    assert int(same_tenant.headers["Retry-After"]) > 0
    assert other_tenant.status_code == 201


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


def test_export_timeout_returns_bounded_gateway_timeout():
    def slow_renderer() -> bytes:
        time.sleep(0.05)
        return b"late"

    with pytest.raises(HTTPException) as timed_out:
        asyncio.run(run_export_with_timeout(slow_renderer, timeout_seconds=0.001))

    assert timed_out.value.status_code == 504


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
