import io
import logging

import pytest
from botocore.exceptions import EndpointConnectionError

from app.middleware import JsonFormatter, _safe_log_request_id
from app.observability.error_tracking import capture_exception, configure_error_tracking
from app.observability.metrics import ObservabilityMetrics
from app.storage.base import StorageUnavailableError
from app.storage.s3 import S3StorageService


def test_metric_names_values_and_low_cardinality_labels():
    registry = ObservabilityMetrics()
    registry.begin_http_request("GET", "unmatched")
    registry.observe_http_request("GET", "/api/v1/reports/{report_id}", 503, 1.6, in_flight_route="unmatched")
    registry.observe_dependency("postgres", "failure")
    registry.set_database_pool(size=5, checked_out=2, overflow=0, capacity=15)
    registry.observe_storage_operation("s3", "upload", "failure", 0.2)
    registry.observe_mfa("challenge", "failure")
    registry.set_database_pool(size=10, checked_out=8, overflow=0, capacity=15)
    registry.set_redis_memory(used_bytes=1024, max_bytes=2048)
    registry.observe_limit_block("upload_quota")
    registry.set_storage_usage_bytes(123)

    rendered = registry.render_prometheus()

    for metric_name in (
        "practiceflow_http_requests_total",
        "practiceflow_http_in_flight_requests",
        "practiceflow_database_pool_connections",
        "practiceflow_database_errors_total",
        "practiceflow_storage_operations_total",
        "practiceflow_mfa_events_total",
        "practiceflow_redis_memory_bytes",
        "practiceflow_limit_blocks_total",
    ):
        assert metric_name in rendered
    assert 'status_class="5xx"' in rendered
    assert 'backend="s3",operation="upload",result="failure"' in rendered
    assert 'practiceflow_database_pool_connections{state="capacity"} 15' in rendered
    assert 'practiceflow_redis_memory_bytes{state="used"} 1024' in rendered
    assert 'reason="upload_quota"' in rendered

    # Caller-provided values can only become "unknown", never labels. This
    # protects Prometheus from accidental PII/high-cardinality additions.
    registry.observe_storage_operation("private-bucket-name", "customer filename.png", "success", 1)
    registry.observe_limit_block("organization-3e5b6f32")
    sanitized = registry.render_prometheus()
    assert "private-bucket-name" not in sanitized
    assert "customer filename.png" not in sanitized
    assert "organization-3e5b6f32" not in sanitized


def test_json_formatter_does_not_write_raw_path_or_exception_message():
    formatter = JsonFormatter()
    record = logging.LogRecord("practiceflow.requests", logging.ERROR, __file__, 1, "request_failed", (), None)
    record.request_id = "request-123"
    record.route = "/api/v1/files/{file_id}"
    record.path = "/api/v1/files/sensitive-file-name.png"
    try:
        raise RuntimeError("token=super-secret email=person@example.test")
    except RuntimeError:
        record.exc_info = __import__("sys").exc_info()
    rendered = formatter.format(record)

    assert '"request_id": "request-123"' in rendered
    assert '"route": "/api/v1/files/{file_id}"' in rendered
    assert "sensitive-file-name.png" not in rendered
    assert "super-secret" not in rendered
    assert "person@example.test" not in rendered
    assert '"exception_type": "RuntimeError"' in rendered
    assert "Bearer-secret-value" not in _safe_log_request_id("Bearer-secret-value")


def test_s3_failure_records_safe_storage_metric(monkeypatch):
    registry = ObservabilityMetrics()
    import app.storage.s3 as s3_module

    monkeypatch.setattr(s3_module, "metrics", registry)

    class BrokenS3:
        def upload_fileobj(self, *_args, **_kwargs):
            raise EndpointConnectionError(endpoint_url="https://private.invalid")

    storage = S3StorageService(client=BrokenS3(), bucket="private-bucket")
    with pytest.raises(StorageUnavailableError):
        storage.save("orgs/opaque/images/object.png", io.BytesIO(b"image"), "image/png")

    rendered = registry.render_prometheus()
    assert 'backend="s3",operation="upload",result="failure"' in rendered
    assert "private-bucket" not in rendered
    assert "private.invalid" not in rendered


def test_sentry_is_noop_when_disabled_and_scrubs_when_enabled():
    class FakeSentry:
        def __init__(self):
            self.initialized = None
            self.captured = []

        def init(self, **kwargs):
            self.initialized = kwargs

        def capture_exception(self, exception):
            self.captured.append(exception)

    fake = FakeSentry()
    assert configure_error_tracking(None, "test", sentry_sdk_module=fake) is False
    assert fake.initialized is None

    assert configure_error_tracking("https://public@example.invalid/1", "test", sentry_sdk_module=fake) is True
    assert fake.initialized["send_default_pii"] is False
    assert fake.initialized["traces_sample_rate"] == 0.0
    scrubbed = fake.initialized["before_send"](
        {
            "request": {"headers": {"authorization": "Bearer secret"}},
            "user": {"email": "person@example.test"},
            "extra": {"file_name": "private.docx"},
            "contexts": {"trace": {"data": "secret"}},
            "breadcrumbs": {"values": [{"message": "private"}]},
            "exception": {"values": [{"type": "RuntimeError", "value": "token", "stacktrace": {}}]},
        },
        {},
    )
    assert "request" not in scrubbed and "user" not in scrubbed and "extra" not in scrubbed and "contexts" not in scrubbed
    assert scrubbed["breadcrumbs"] == {"values": []}
    assert scrubbed["exception"]["values"][0] == {"type": "RuntimeError"}
    exception = RuntimeError("never exported")
    capture_exception(exception)
    assert fake.captured == [exception]
    configure_error_tracking(None, "test")
