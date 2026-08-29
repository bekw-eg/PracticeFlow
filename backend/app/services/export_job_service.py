"""Durable, tenant-scoped export-job lifecycle.

The PostgreSQL row is authoritative. Redis only wakes a worker, so duplicate
messages and worker restarts cannot create a second active export or grant
access to an artifact from a different organization.
"""
from __future__ import annotations

import uuid
import time
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.dependencies.auth import RequestContext
from app.export_queue import ExportQueue
from app.models.enums import AuditEventType, ExportFormat, ExportJobStatus
from app.models.export_job import ExportJob
from app.observability.metrics import metrics
from app.resource_protection import ResourceGuard
from app.services.audit_service import AuditService
from app.services.export_service import ExportService
from app.storage import get_storage_service


TERMINAL_STATUSES = {
    ExportJobStatus.SUCCEEDED,
    ExportJobStatus.FAILED,
    ExportJobStatus.TIMED_OUT,
    ExportJobStatus.CANCELLED,
}
ACTIVE_STATUSES = {ExportJobStatus.QUEUED, ExportJobStatus.RUNNING}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def format_value(value: ExportFormat | str) -> str:
    return value.value if isinstance(value, ExportFormat) else value


class ExportJobService:
    def __init__(self, db: Session):
        self.db = db
        self.storage = get_storage_service()

    @staticmethod
    def _dedupe_key(report_id: uuid.UUID, export_format: ExportFormat) -> str:
        return f"report:{report_id}:{export_format.value}"

    def _authorize(self, ctx: RequestContext, report_id: uuid.UUID):
        return ExportService(self.db).get_authorized_report(
            ctx.organization_id, ctx.role, ctx.teacher_id, ctx.student_id, report_id
        )

    def create(self, ctx: RequestContext, report_id: uuid.UUID, export_format: ExportFormat, guard: ResourceGuard, queue: ExportQueue) -> tuple[ExportJob, bool]:
        # Do authorization and document validation while an HTTP context is
        # available. The worker repeats authorization before it renders.
        report = self._authorize(ctx, report_id)
        if report.document_data is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Report has no document content to export yet.")
        guard.check_export_rate(ctx.organization_id, ctx.user_id)
        dedupe_key = self._dedupe_key(report_id, export_format)
        existing = self.db.execute(
            select(ExportJob).where(
                ExportJob.organization_id == ctx.organization_id,
                ExportJob.dedupe_key == dedupe_key,
                ExportJob.status.in_(ACTIVE_STATUSES),
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing, True

        job = ExportJob(
            organization_id=ctx.organization_id,
            report_id=report_id,
            requested_by_user_id=ctx.user_id,
            requested_role=ctx.role,
            format=export_format,
            status=ExportJobStatus.QUEUED,
            dedupe_key=dedupe_key,
            expires_at=utcnow() + timedelta(seconds=settings.EXPORT_JOB_RETENTION_SECONDS),
        )
        try:
            self.db.add(job)
            self.db.flush()
            AuditService(self.db).record(
                organization_id=ctx.organization_id,
                actor_user_id=ctx.user_id,
                event_type=AuditEventType.EXPORT_REQUESTED,
                entity_type="report",
                entity_id=report_id,
                metadata={"format": export_format.value.upper()},
                correlation_id=str(job.id),
            )
            self.db.commit()
            self.db.refresh(job)
        except IntegrityError:
            # PostgreSQL's partial unique index closes the race between two
            # API replicas; return the job which won rather than enqueueing a
            # second render.
            self.db.rollback()
            existing = self.db.execute(
                select(ExportJob).where(
                    ExportJob.organization_id == ctx.organization_id,
                    ExportJob.dedupe_key == dedupe_key,
                    ExportJob.status.in_(ACTIVE_STATUSES),
                )
            ).scalar_one_or_none()
            if existing is None:
                raise
            return existing, True

        try:
            queue.enqueue(str(job.id))
        except HTTPException:
            job.status = ExportJobStatus.FAILED
            job.error_code = "EXPORT_QUEUE_UNAVAILABLE"
            job.finished_at = utcnow()
            self.db.commit()
            metrics.observe_export_transition(format_value(job.format), ExportJobStatus.FAILED.value)
            raise
        metrics.observe_export_transition(format_value(job.format), ExportJobStatus.QUEUED.value)
        return job, False

    def get_authorized(self, ctx: RequestContext, job_id: uuid.UUID) -> ExportJob:
        job = self.db.execute(
            select(ExportJob).where(ExportJob.id == job_id, ExportJob.organization_id == ctx.organization_id)
        ).scalar_one_or_none()
        if job is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export job not found")
        # Source-report authorization is deliberately reapplied for status and
        # download, avoiding historical-artifact bypass after access changed.
        self._authorize(ctx, job.report_id)
        return job

    def cancel(self, ctx: RequestContext, job_id: uuid.UUID) -> ExportJob:
        job = self.get_authorized(ctx, job_id)
        if job.status == ExportJobStatus.QUEUED:
            job.status = ExportJobStatus.CANCELLED
            job.finished_at = utcnow()
        elif job.status == ExportJobStatus.RUNNING:
            job.cancel_requested_at = utcnow()
        self.db.commit()
        self.db.refresh(job)
        if job.status == ExportJobStatus.CANCELLED:
            metrics.observe_export_transition(format_value(job.format), ExportJobStatus.CANCELLED.value)
        return job

    def claim(self, job_id: uuid.UUID, worker_id: str) -> ExportJob | None:
        job = self.db.execute(select(ExportJob).where(ExportJob.id == job_id).with_for_update()).scalar_one_or_none()
        if job is None or job.status != ExportJobStatus.QUEUED:
            self.db.rollback()
            return None
        now = utcnow()
        job.status = ExportJobStatus.RUNNING
        job.worker_id = worker_id
        job.started_at = now
        job.lease_expires_at = now + timedelta(seconds=settings.EXPORT_WORKER_LEASE_SECONDS)
        job.storage_key = f"orgs/{job.organization_id}/exports/{job.id}.{format_value(job.format)}"
        self.db.commit()
        self.db.refresh(job)
        metrics.observe_export_transition(format_value(job.format), ExportJobStatus.RUNNING.value)
        return job

    def heartbeat(self, job_id: uuid.UUID, worker_id: str) -> bool:
        job = self.db.execute(select(ExportJob).where(ExportJob.id == job_id).with_for_update()).scalar_one_or_none()
        if job is None or job.status != ExportJobStatus.RUNNING or job.worker_id != worker_id:
            self.db.rollback()
            return False
        job.lease_expires_at = utcnow() + timedelta(seconds=settings.EXPORT_WORKER_LEASE_SECONDS)
        self.db.commit()
        return job.cancel_requested_at is None

    def requeue_claim(self, job_id: uuid.UUID, worker_id: str) -> bool:
        """Return an owned running job to the durable queue on graceful stop."""
        job = self.db.execute(select(ExportJob).where(ExportJob.id == job_id).with_for_update()).scalar_one_or_none()
        if job is None or job.status != ExportJobStatus.RUNNING or job.worker_id != worker_id:
            self.db.rollback()
            return False
        job.status = ExportJobStatus.QUEUED
        job.worker_id = None
        job.started_at = None
        job.lease_expires_at = None
        self.db.commit()
        metrics.observe_export_transition(format_value(job.format), ExportJobStatus.QUEUED.value)
        metrics.observe_export_retry("graceful_shutdown")
        return True

    def finish(self, job_id: uuid.UUID, job_status: ExportJobStatus, error_code: str | None = None, *, content_type: str | None = None, size_bytes: int | None = None) -> ExportJob | None:
        job = self.db.execute(select(ExportJob).where(ExportJob.id == job_id).with_for_update()).scalar_one_or_none()
        if job is None or job.status in TERMINAL_STATUSES:
            self.db.rollback()
            return None
        final_status = ExportJobStatus.CANCELLED if job.cancel_requested_at else job_status
        job.status = final_status
        job.error_code = error_code if final_status != ExportJobStatus.CANCELLED else None
        job.content_type = content_type if final_status == ExportJobStatus.SUCCEEDED else None
        job.size_bytes = size_bytes if final_status == ExportJobStatus.SUCCEEDED else None
        job.finished_at = utcnow()
        job.lease_expires_at = None
        if final_status == ExportJobStatus.SUCCEEDED:
            event = AuditEventType.DOCX_GENERATED if format_value(job.format) == ExportFormat.DOCX.value else AuditEventType.PDF_GENERATED
            AuditService(self.db).record(
                organization_id=job.organization_id,
                actor_user_id=job.requested_by_user_id,
                event_type=event,
                entity_type="report",
                entity_id=job.report_id,
                metadata={"format": format_value(job.format).upper(), "size_bytes": size_bytes or 0},
                correlation_id=str(job.id),
            )
        self.db.commit()
        self.db.refresh(job)
        metrics.observe_export_transition(format_value(job.format), final_status.value)
        if job.started_at is not None:
            metrics.observe_export_duration(format_value(job.format), final_status.value, (job.finished_at - job.started_at).total_seconds())
        return job

    def record_download(self, ctx: RequestContext, job: ExportJob) -> None:
        AuditService(self.db).record(
            organization_id=ctx.organization_id,
            actor_user_id=ctx.user_id,
            event_type=AuditEventType.EXPORT_DOWNLOADED,
            entity_type="report",
            entity_id=job.report_id,
            metadata={"format": format_value(job.format).upper(), "size_bytes": job.size_bytes or 0},
            correlation_id=str(job.id),
        )
        self.db.commit()

    def recover_stale(self, queue: ExportQueue) -> int:
        """Make jobs from a dead worker available again; stale messages are safe."""
        now = utcnow()
        jobs = list(self.db.execute(
            select(ExportJob).where(
                (ExportJob.status == ExportJobStatus.QUEUED)
                | ((ExportJob.status == ExportJobStatus.RUNNING) & (ExportJob.lease_expires_at < now))
            )
        ).scalars())
        stale_recoveries = 0
        for job in jobs:
            if job.status == ExportJobStatus.RUNNING:
                job.status = ExportJobStatus.QUEUED
                job.worker_id = None
                job.started_at = None
                job.lease_expires_at = None
                stale_recoveries += 1
        self.db.commit()
        delivered = 0
        for job in jobs:
            if job.status == ExportJobStatus.QUEUED:
                queue.enqueue(str(job.id))
                delivered += 1
        for _ in range(stale_recoveries):
            metrics.observe_export_stale_recovery()
            metrics.observe_export_retry("stale_worker")
        return delivered

    def cleanup_expired(self) -> int:
        now = utcnow()
        jobs = list(self.db.execute(select(ExportJob).where(ExportJob.expires_at < now, ExportJob.status.in_(TERMINAL_STATUSES))).scalars())
        removed = 0
        for job in jobs:
            if job.storage_key:
                started = time.perf_counter()
                try:
                    self.storage.delete(job.storage_key)
                except Exception:
                    metrics.observe_storage_operation(
                        "s3" if settings.STORAGE_BACKEND == "s3" else "local", "cleanup", "failure", time.perf_counter() - started
                    )
                    # Do not drop the durable record if retention cleanup was
                    # unable to remove bytes. A later cleanup retry is safe.
                    continue
                metrics.observe_storage_operation(
                    "s3" if settings.STORAGE_BACKEND == "s3" else "local", "cleanup", "success", time.perf_counter() - started
                )
            AuditService(self.db).record(
                organization_id=job.organization_id,
                actor_user_id=None,
                event_type=AuditEventType.EXPORT_FILE_DELETED,
                entity_type="export_job",
                entity_id=job.id,
                metadata={"format": format_value(job.format).upper()},
                correlation_id=str(job.id),
            )
            self.db.delete(job)
            removed += 1
        self.db.commit()
        return removed
