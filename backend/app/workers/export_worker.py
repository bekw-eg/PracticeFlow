"""Redis-driven export worker with a killable renderer subprocess.

The worker is intentionally a separate Compose service. Every render gets a
short-lived child process; timeout/cancel force that process to stop before a
job is marked terminal, so a wedged renderer cannot keep consuming CPU.
"""
from __future__ import annotations

import argparse
import io
import logging
import multiprocessing
import queue as stdlib_queue
import signal
import time
import uuid
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.engine import create_database_engine
from app.export_queue import ExportQueue
from app.middleware import configure_structured_logging
from app.models.enums import ExportJobStatus
from app.models.export_job import ExportJob
from app.observability.error_tracking import capture_exception, configure_error_tracking
from app.observability.metrics import metrics
from app.rate_limit.dependencies import get_export_queue, get_resource_guard
from app.resource_protection import ExportLease, ResourceGuard
from app.services.export_job_service import ExportJobService
from app.services.audit_service import AuditService
from app.services.export_service import ExportService
from app.storage import get_storage_service
from app.workers.heartbeat import WorkerHeartbeat, default_worker_id, get_worker_heartbeat

log = logging.getLogger("practiceflow.export_worker")


def _render_child(job_id: str, database_url: str, result_queue) -> None:
    """Child target: no parent DB session or Redis lease crosses this boundary."""
    configure_structured_logging(settings.LOG_LEVEL)
    configure_error_tracking(settings.SENTRY_DSN, settings.SENTRY_ENVIRONMENT or settings.ENV)
    engine = create_database_engine(database_url, worker=True)
    local_session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    try:
        with local_session() as db:
            job = db.get(ExportJob, uuid.UUID(job_id))
            if job is None:
                result_queue.put(("error", "EXPORT_JOB_NOT_FOUND"))
                return
            data, content_type = ExportService(db).render_for_job(job)
            if not job.storage_key:
                result_queue.put(("error", "EXPORT_STORAGE_KEY_MISSING"))
                return
            get_storage_service().save(job.storage_key, io.BytesIO(data), content_type)
            result_queue.put(("success", len(data), content_type))
    except HTTPException as exc:
        # Error codes, rather than raw internal strings, are persisted and
        # presented to users. Structured logs retain only exception types.
        result_queue.put(("error", f"EXPORT_HTTP_{exc.status_code}"))
    except Exception as exc:
        capture_exception(exc)
        log.exception("export_renderer_child_failed", extra={"export_job_id": job_id, "component": "export_worker"})
        result_queue.put(("error", "EXPORT_RENDER_FAILED"))
    finally:
        engine.dispose()


class ExportWorker:
    def __init__(
        self,
        session_factory,
        export_queue: ExportQueue,
        guard: ResourceGuard,
        worker_id: str | None = None,
        heartbeat: WorkerHeartbeat | None = None,
    ):
        self.session_factory = session_factory
        self.queue = export_queue
        self.guard = guard
        self.worker_id = worker_id or default_worker_id()
        self.heartbeat = heartbeat or get_worker_heartbeat()
        self.stopping = False
        self._next_heartbeat = 0.0
        self._next_audit_cleanup = 0.0

    def _service(self) -> tuple[Session, ExportJobService]:
        db = self.session_factory()
        return db, ExportJobService(db)

    def _beat(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now < self._next_heartbeat:
            return
        try:
            self.heartbeat.beat(self.worker_id)
        except Exception as exc:
            capture_exception(exc)
            log.exception("export_worker_heartbeat_failed", extra={"component": "export_worker"})
        finally:
            self._next_heartbeat = now + settings.EXPORT_WORKER_HEARTBEAT_INTERVAL_SECONDS

    @staticmethod
    def _stop_process(process) -> None:
        if process.is_alive():
            process.terminate()
            process.join(timeout=2)
        if process.is_alive():
            process.kill()
            process.join(timeout=2)

    def process_job(self, job_id: str) -> None:
        db, service = self._service()
        lease: ExportLease | None = None
        process = None
        result_queue = None
        claimed = None
        try:
            self._beat(force=True)
            claimed = service.claim(uuid.UUID(job_id), self.worker_id)
            if claimed is None:
                return
            try:
                lease = self.guard.acquire_export_slot(claimed.organization_id, claimed.requested_by_user_id)
            except HTTPException as exc:
                # A job has not rendered yet. Put it back in the durable queue
                # only after its lease/slot owner has had time to make progress.
                claimed.status = ExportJobStatus.QUEUED
                claimed.worker_id = None
                claimed.lease_expires_at = None
                db.commit()
                metrics.observe_export_retry("concurrency")
                time.sleep(max(1, int(exc.headers.get("Retry-After", settings.EXPORT_WORKER_REQUEUE_DELAY_SECONDS))))
                self.queue.enqueue(job_id)
                return

            ctx = multiprocessing.get_context("spawn")
            result_queue = ctx.Queue(maxsize=1)
            # str(URL) intentionally redacts passwords for logs. The spawned
            # renderer needs the real isolated connection URL, so render it
            # explicitly and never log this value.
            database_url = db.get_bind().url.render_as_string(hide_password=False)
            process = ctx.Process(target=_render_child, args=(job_id, database_url, result_queue), daemon=False)
            process.start()
            deadline = time.monotonic() + settings.EXPORT_WORKER_HARD_TIMEOUT_SECONDS
            cancelled = False
            while process.is_alive():
                process.join(timeout=0.25)
                self._beat()
                if self.stopping:
                    self._stop_process(process)
                    if service.requeue_claim(claimed.id, self.worker_id):
                        self.queue.enqueue(job_id)
                    return
                if not service.heartbeat(claimed.id, self.worker_id):
                    cancelled = True
                    break
                if time.monotonic() >= deadline:
                    self._stop_process(process)
                    service.finish(claimed.id, ExportJobStatus.TIMED_OUT, "EXPORT_HARD_TIMEOUT")
                    if claimed.storage_key:
                        get_storage_service().delete(claimed.storage_key)
                    return
            if cancelled:
                self._stop_process(process)
                service.finish(claimed.id, ExportJobStatus.CANCELLED)
                if claimed.storage_key:
                    get_storage_service().delete(claimed.storage_key)
                return
            process.join(timeout=1)
            try:
                outcome = result_queue.get(timeout=1)
            except stdlib_queue.Empty:
                outcome = ("error", "EXPORT_RENDERER_EXITED")
            if outcome[0] == "success":
                final_job = service.finish(claimed.id, ExportJobStatus.SUCCEEDED, content_type=outcome[2], size_bytes=outcome[1])
                if final_job is not None and final_job.status != ExportJobStatus.SUCCEEDED and claimed.storage_key:
                    get_storage_service().delete(claimed.storage_key)
            else:
                service.finish(claimed.id, ExportJobStatus.FAILED, outcome[1])
        except Exception as exc:
            capture_exception(exc)
            log.exception("export_worker_job_failed", extra={"export_job_id": job_id, "component": "export_worker"})
            if claimed is not None:
                try:
                    service.finish(claimed.id, ExportJobStatus.FAILED, "EXPORT_WORKER_FAILURE")
                except Exception as finish_exc:
                    capture_exception(finish_exc)
                    log.exception("export_worker_mark_failed_failed", extra={"export_job_id": job_id, "component": "export_worker"})
        finally:
            if process is not None:
                self._stop_process(process)
            if lease is not None:
                try:
                    self.guard.release_export(lease)
                except Exception as release_exc:
                    capture_exception(release_exc)
                    log.exception("export_worker_slot_release_failed", extra={"export_job_id": job_id, "component": "export_worker"})
            if result_queue is not None:
                result_queue.close()
            db.close()

    def recover(self) -> int:
        db, service = self._service()
        try:
            return service.recover_stale(self.queue)
        finally:
            db.close()

    def cleanup(self) -> int:
        db, service = self._service()
        try:
            return service.cleanup_expired()
        finally:
            db.close()

    def cleanup_audit(self) -> int:
        db = self.session_factory()
        try:
            return AuditService(db).cleanup_expired(settings.AUDIT_RETENTION_DAYS)
        finally:
            db.close()

    def run_forever(self) -> None:
        self._beat(force=True)
        self.recover()
        next_maintenance = time.monotonic()
        self._next_audit_cleanup = time.monotonic()
        while not self.stopping:
            try:
                self._beat()
                job_id = self.queue.dequeue(settings.EXPORT_WORKER_QUEUE_TIMEOUT_SECONDS)
                if job_id:
                    self.process_job(job_id)
                if time.monotonic() >= next_maintenance:
                    self.recover()
                    self.cleanup()
                    next_maintenance = time.monotonic() + 30
                if time.monotonic() >= self._next_audit_cleanup:
                    self.cleanup_audit()
                    self._next_audit_cleanup = time.monotonic() + settings.AUDIT_CLEANUP_INTERVAL_SECONDS
            except HTTPException as exc:
                capture_exception(exc)
                log.exception("export_queue_unavailable", extra={"component": "export_worker"})
                time.sleep(1)
            except Exception as exc:
                capture_exception(exc)
                log.exception("export_worker_loop_failed", extra={"component": "export_worker"})
                time.sleep(1)


def _healthcheck() -> int:
    try:
        engine = create_database_engine(worker=True)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        engine.dispose()
        if not get_export_queue().ping() or not get_resource_guard().ping() or not get_storage_service().ping():
            return 1
        return 0
    except Exception as exc:
        capture_exception(exc)
        log.exception("export_worker_healthcheck_failed", extra={"component": "export_worker"})
        return 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="check worker dependencies and exit")
    args = parser.parse_args()
    configure_structured_logging(settings.LOG_LEVEL)
    configure_error_tracking(settings.SENTRY_DSN, settings.SENTRY_ENVIRONMENT or settings.ENV)
    if args.check:
        raise SystemExit(_healthcheck())
    factory = sessionmaker(bind=create_database_engine(worker=True), autoflush=False, autocommit=False, future=True)
    worker = ExportWorker(factory, get_export_queue(), get_resource_guard())
    signal.signal(signal.SIGTERM, lambda *_args: setattr(worker, "stopping", True))
    signal.signal(signal.SIGINT, lambda *_args: setattr(worker, "stopping", True))
    worker.run_forever()


if __name__ == "__main__":
    main()
