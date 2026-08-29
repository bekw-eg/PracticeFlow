import json
import hashlib
import logging
import re
import time
import uuid
from datetime import UTC, datetime

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.audit_context import reset_request_audit_context, set_request_audit_context
from app.observability.metrics import metrics


logger = logging.getLogger("practiceflow.requests")
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def _safe_log_request_id(request_id: str) -> str:
    """Keep request correlation without logging a client-supplied secret."""
    return "sha256:" + hashlib.sha256(request_id.encode("utf-8")).hexdigest()[:24]


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            # All PracticeFlow messages are event names. Do not call
            # ``getMessage``: third-party exception arguments can contain a
            # database URL, object key, or user-provided content.
            "message": str(record.msg),
        }
        for field in ("request_id", "export_job_id", "route", "method", "status_code", "duration_ms", "component", "operation", "result"):
            if hasattr(record, field):
                payload[field] = getattr(record, field)
        if record.exc_info:
            payload["exception_type"] = type(record.exc_info[1]).__name__
        return json.dumps(payload, ensure_ascii=False)


def configure_structured_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    application_logger = logging.getLogger("practiceflow")
    application_logger.handlers.clear()
    application_logger.addHandler(handler)
    application_logger.setLevel(level.upper())
    application_logger.propagate = False


class RequestObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming_id = request.headers.get("X-Request-ID", "")
        request_id = incoming_id if _REQUEST_ID_PATTERN.fullmatch(incoming_id) else str(uuid.uuid4())
        request.state.request_id = request_id
        audit_context_token = set_request_audit_context(
            request_id,
            request.client.host if request.client else None,
        )
        started = time.perf_counter()
        in_flight_route = "unmatched"
        metrics.begin_http_request(request.method, in_flight_route)
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            duration = time.perf_counter() - started
            route = request.scope.get("route")
            route_path = getattr(route, "path", "unmatched")
            metrics.observe_http_request(
                request.method,
                route_path,
                status_code,
                duration,
                in_flight_route=in_flight_route,
            )
            logger.info(
                "http_request",
                extra={
                    "request_id": _safe_log_request_id(request_id),
                    "method": request.method,
                    "route": route_path,
                    "status_code": status_code,
                    "duration_ms": round(duration * 1000, 2),
                },
            )
            reset_request_audit_context(audit_context_token)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        is_api_docs = request.url.path in {"/docs", "/redoc"}
        if is_api_docs:
            csp = (
                "default-src 'none'; base-uri 'none'; frame-ancestors 'none'; "
                "img-src 'self' data: https://fastapi.tiangolo.com; "
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "font-src 'self' https://cdn.jsdelivr.net; connect-src 'self'"
            )
        else:
            csp = "default-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'"
        response.headers["Content-Security-Policy"] = csp
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
        return response
