from app.services.notification_service import NotificationService
from app.tests.conftest import OrgFixture, auth_headers


def test_security_headers_and_correlation_id(client, org_a: OrgFixture):
    response = client.get("/health", headers={"X-Request-ID": "test-request-123"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "test-request-123"
    assert "default-src 'none'" in response.headers["Content-Security-Policy"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "camera=()" in response.headers["Permissions-Policy"]


def test_invalid_correlation_id_is_replaced(client, org_a: OrgFixture):
    response = client.get("/health", headers={"X-Request-ID": "bad id with spaces"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] != "bad id with spaces"


def test_readiness_checks_database_and_rate_limiter(client, org_a: OrgFixture):
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "database": "ok",
        "rate_limit_backend": "ok",
        "resource_protection_backend": "ok",
        "export_queue": "ok",
        "storage_backend": "ok",
    }


def test_metrics_are_prometheus_compatible(client, org_a: OrgFixture):
    client.get("/health")
    response = client.get("/metrics")

    assert response.status_code == 200
    assert "practiceflow_http_requests_total" in response.text
    assert 'route="/health"' in response.text


def test_list_endpoints_apply_bounded_pagination(client, db, org_a: OrgFixture):
    service = NotificationService(db)
    for number in range(3):
        service.create(org_a.org.id, org_a.teacher_user.id, "TEST", f"Notification {number}")
    db.commit()
    token = org_a.teacher_token(client)

    response = client.get("/api/v1/notifications?offset=1&limit=1", headers=auth_headers(token))

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.headers["X-Total-Count"] == "3"
    assert response.headers["X-Has-More"] == "true"
    invalid = client.get("/api/v1/notifications?limit=201", headers=auth_headers(token))
    assert invalid.status_code == 422


def test_cors_allows_credentialed_frontend_requests(client, org_a: OrgFixture):
    response = client.options(
        "/api/v1/auth/refresh",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Credentials"] == "true"
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"

    # Exposed response headers are attached to the actual CORS response, not
    # the OPTIONS preflight response.
    actual = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert "x-total-count" in actual.headers["Access-Control-Expose-Headers"].lower()
