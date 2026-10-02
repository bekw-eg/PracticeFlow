from fastapi import Depends, FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.api.v1.router import api_router
from app.api.pagination import PAGINATION_RESPONSE_HEADERS
from app.core.config import settings
from app.db.session import get_db, update_pool_metrics
from app.document_submission_limits import DocumentSubmissionBodyLimitMiddleware
from app.middleware import RequestObservabilityMiddleware, SecurityHeadersMiddleware, configure_structured_logging
from app.models.export_job import ExportJob
from app.models.file import File
from app.models.document_check import StudentDocumentSubmission, TeacherDocumentSubmission, TeacherDocumentLifecycle
from app.observability.error_tracking import configure_error_tracking
from app.observability.metrics import metrics as observability_metrics
from app.observability.redis_memory import observe_redis_memory
from app.rate_limit.base import LoginRateLimiter
from app.rate_limit.dependencies import get_export_queue, get_login_rate_limiter, get_resource_guard
from app.export_queue import ExportQueue
from app.resource_protection import ResourceGuard
from app.storage import get_storage_service
from app.workers.heartbeat import get_worker_heartbeat

app = FastAPI(title=settings.PROJECT_NAME, openapi_url=f"{settings.API_V1_PREFIX}/openapi.json")
configure_structured_logging(settings.LOG_LEVEL)
configure_error_tracking(settings.SENTRY_DSN, settings.SENTRY_ENVIRONMENT or settings.ENV)

app.add_middleware(DocumentSubmissionBodyLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", *PAGINATION_RESPONSE_HEADERS],
)
app.add_middleware(RequestObservabilityMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
# Uvicorn itself is started with --no-proxy-headers.  This middleware is the
# single, explicitly configured place that may turn forwarded headers into a
# client address.  An empty development allow-list trusts no client headers.
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=settings.TRUSTED_PROXY_IPS)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/health")
@app.get("/health/live")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", response_model=None)
def readiness(
    db: Session = Depends(get_db),
    limiter: LoginRateLimiter = Depends(get_login_rate_limiter),
    resource_guard: ResourceGuard = Depends(get_resource_guard),
    export_queue: ExportQueue = Depends(get_export_queue),
) -> dict[str, str] | JSONResponse:
    checks = {
        "database": "ok",
        "rate_limit_backend": "ok",
        "resource_protection_backend": "ok",
        "export_queue": "ok",
        "storage_backend": "ok",
    }
    try:
        db.execute(text("SELECT 1"))
        observability_metrics.observe_dependency("postgres", "success")
        update_pool_metrics()
    except Exception:
        checks["database"] = "unavailable"
        observability_metrics.observe_dependency("postgres", "failure")
    try:
        if not limiter.ping():
            checks["rate_limit_backend"] = "unavailable"
        observability_metrics.observe_dependency("redis_rate_limit", "success" if checks["rate_limit_backend"] == "ok" else "failure")
    except Exception:
        checks["rate_limit_backend"] = "unavailable"
        observability_metrics.observe_dependency("redis_rate_limit", "failure")
    try:
        if not resource_guard.ping():
            checks["resource_protection_backend"] = "unavailable"
        observability_metrics.observe_dependency("redis_resource_guard", "success" if checks["resource_protection_backend"] == "ok" else "failure")
    except Exception:
        checks["resource_protection_backend"] = "unavailable"
        observability_metrics.observe_dependency("redis_resource_guard", "failure")
    try:
        if not export_queue.ping():
            checks["export_queue"] = "unavailable"
        observability_metrics.observe_dependency("redis_export_queue", "success" if checks["export_queue"] == "ok" else "failure")
    except Exception:
        checks["export_queue"] = "unavailable"
        observability_metrics.observe_dependency("redis_export_queue", "failure")
    try:
        if not get_storage_service().ping():
            checks["storage_backend"] = "unavailable"
        observability_metrics.observe_dependency("s3" if settings.STORAGE_BACKEND == "s3" else "local_storage", "success" if checks["storage_backend"] == "ok" else "failure")
    except Exception:
        checks["storage_backend"] = "unavailable"
        observability_metrics.observe_dependency("s3" if settings.STORAGE_BACKEND == "s3" else "local_storage", "failure")
    if "unavailable" in checks.values():
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content={"status": "not_ready", "checks": checks})
    return {"status": "ready", **checks}


@app.get("/health/worker/export", response_model=None)
def export_worker_readiness() -> dict[str, int | float | str] | JSONResponse:
    age_seconds, active_workers = get_worker_heartbeat().snapshot()
    observability_metrics.set_worker_heartbeat(age_seconds, active_workers)
    if age_seconds is None or age_seconds > settings.EXPORT_WORKER_HEARTBEAT_TTL_SECONDS:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "not_ready", "worker": "export", "active_workers": active_workers},
        )
    return {"status": "ready", "worker": "export", "active_workers": active_workers, "heartbeat_age_seconds": age_seconds}


@app.get("/metrics", response_class=PlainTextResponse, include_in_schema=False)
def prometheus_metrics(
    db: Session = Depends(get_db),
    export_queue: ExportQueue = Depends(get_export_queue),
) -> str:
    try:
        states = {
            getattr(job_status, "value", str(job_status)): count
            for job_status, count in db.execute(select(ExportJob.status, func.count()).group_by(ExportJob.status)).all()
        }
        storage_usage = db.scalar(select(func.coalesce(func.sum(File.size_bytes), 0))) or 0
        storage_usage += db.scalar(select(func.coalesce(func.sum(StudentDocumentSubmission.size_bytes), 0))) or 0
        storage_usage += db.scalar(select(func.coalesce(func.sum(TeacherDocumentSubmission.size_bytes), 0)).where(
            ~TeacherDocumentSubmission.lifecycle.has(TeacherDocumentLifecycle.original_deleted_at.is_not(None)),
        )) or 0
        observability_metrics.set_export_job_states(states)
        observability_metrics.set_storage_usage_bytes(int(storage_usage))
        observability_metrics.observe_dependency("postgres", "success")
        update_pool_metrics()
    except Exception:
        observability_metrics.observe_dependency("postgres", "failure")
    try:
        observability_metrics.set_export_queue_depth(export_queue.depth())
        observability_metrics.observe_dependency("redis_export_queue", "success")
    except Exception:
        observability_metrics.observe_dependency("redis_export_queue", "failure")
    age_seconds, active_workers = get_worker_heartbeat().snapshot()
    observability_metrics.set_worker_heartbeat(age_seconds, active_workers)
    observe_redis_memory()
    return observability_metrics.render_prometheus()
