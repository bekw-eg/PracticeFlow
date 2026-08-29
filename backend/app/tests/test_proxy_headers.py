from unittest.mock import patch

from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.api.v1 import auth as auth_module
from app.db.session import get_db
from app.main import app as practiceflow_app
from app.rate_limit.dependencies import get_login_rate_limiter


def _client_echo_app(trusted_hosts: str) -> FastAPI:
    application = FastAPI()
    application.add_middleware(ProxyHeadersMiddleware, trusted_hosts=trusted_hosts)

    @application.get("/client")
    def client(request: Request) -> dict[str, str]:
        assert request.client is not None
        return {"host": request.client.host, "scheme": request.url.scheme}

    return application


def test_proxy_headers_ignore_a_forged_xff_from_an_untrusted_peer():
    application = _client_echo_app("172.30.0.10,172.30.0.11")
    with TestClient(application, client=("198.51.100.25", 40000)) as client:
        response = client.get("/client", headers={"X-Forwarded-For": "203.0.113.200", "X-Forwarded-Proto": "https"})

    assert response.json() == {"host": "198.51.100.25", "scheme": "http"}


def test_proxy_headers_accept_the_client_ip_only_through_explicit_proxy_hops():
    application = _client_echo_app("172.30.0.10,172.30.0.11")
    with TestClient(application, client=("172.30.0.10", 40000)) as client:
        response = client.get(
            "/client",
            headers={"X-Forwarded-For": "198.51.100.25, 172.30.0.11", "X-Forwarded-Proto": "https"},
        )

    assert response.json() == {"host": "198.51.100.25", "scheme": "https"}


class _FakeLoginRateLimiter:
    def __init__(self) -> None:
        self.failures = 0

    def is_blocked(self, key: str) -> bool:
        return self.failures >= 2

    def record_failure(self, key: str) -> None:
        self.failures += 1

    def reset(self, key: str) -> None:
        self.failures = 0


def test_spoofed_xff_cannot_bypass_the_login_rate_limit():
    """HTTP-level regression: TestClient is an untrusted direct peer, so XFF
    must not create a new rate-limit key for each failed password attempt."""

    limiter = _FakeLoginRateLimiter()

    def override_db():
        yield object()

    def reject_login(*_args, **_kwargs):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    practiceflow_app.dependency_overrides[get_db] = override_db
    practiceflow_app.dependency_overrides[get_login_rate_limiter] = lambda: limiter
    payload = {"email": "rate-limit@example.com", "password": "wrong-password", "organization_slug": "org"}
    try:
        with patch.object(auth_module.AuthService, "login", side_effect=reject_login):
            with TestClient(practiceflow_app, client=("198.51.100.25", 40000)) as client:
                assert client.post("/api/v1/auth/login", json=payload, headers={"X-Forwarded-For": "203.0.113.10"}).status_code == 401
                assert client.post("/api/v1/auth/login", json=payload, headers={"X-Forwarded-For": "203.0.113.11"}).status_code == 401
                assert client.post("/api/v1/auth/login", json=payload, headers={"X-Forwarded-For": "203.0.113.12"}).status_code == 429
    finally:
        practiceflow_app.dependency_overrides.clear()
