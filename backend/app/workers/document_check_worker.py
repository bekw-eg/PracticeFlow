"""Independent durable DOCX analyzer worker; it never uses the export queue."""
from __future__ import annotations

import argparse
import hashlib
import logging
import multiprocessing
import queue
import signal
import tempfile
import time
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.engine import create_database_engine
from app.middleware import configure_structured_logging
from app.observability.error_tracking import capture_exception, configure_error_tracking
from app.services.document_analyzer import AnalyzerFinding, AnalyzerRule, analyze_document
from app.services.document_check_job_service import DocumentCheckJobService
from app.services.local_plagiarism_service import LocalPlagiarismService, extract_local_similarity_paragraphs
from app.storage import get_storage_service
from app.storage.base import StorageUnavailableError
from app.workers.heartbeat import default_worker_id

log = logging.getLogger("practiceflow.document_check_worker")


class _OriginalIntegrityError(Exception):
    pass


class _LeaseLost(Exception):
    pass


def _stage_and_analyze_child(
    path, storage, storage_key, expected_size, expected_sha, max_upload_bytes,
    rules, max_findings, paragraph_overrides, result_queue,
) -> None:
    """Storage I/O is covered by the same hard deadline as format analysis."""
    try:
        storage = storage if storage is not None else get_storage_service()
        digest = hashlib.sha256()
        size = 0
        source = storage.open(storage_key)
        try:
            with Path(path).open("xb") as target:
                while chunk := source.read(64 * 1024):
                    size += len(chunk)
                    if size > max_upload_bytes:
                        raise _OriginalIntegrityError
                    digest.update(chunk)
                    target.write(chunk)
        finally:
            source.close()
        if size != expected_size or digest.hexdigest() != expected_sha:
            raise _OriginalIntegrityError
    except _OriginalIntegrityError:
        result_queue.put(("error", "CHECK_ORIGINAL_INTEGRITY"))
        return
    except (StorageUnavailableError, FileNotFoundError, OSError):
        result_queue.put(("error", "CHECK_STORAGE_UNAVAILABLE"))
        return
    _analyze_child(path, rules, max_findings, result_queue, paragraph_overrides)


def _analyze_child(
    path: str, rules: list[AnalyzerRule], max_findings: int, result_queue,
    paragraph_overrides=None,
) -> None:
    try:
        findings, summary = analyze_document(path, rules, max_findings=max_findings, paragraph_overrides=paragraph_overrides)
        result_queue.put(("success", [finding.as_dict() for finding in findings], summary))
    except Exception as exc:
        capture_exception(exc)
        log.exception("document_analyzer_child_failed", extra={"component": "document_check_worker"})
        result_queue.put(("error", "CHECK_ANALYSIS_FAILED"))


def _similarity_child(path, database_url, job_id, worker_id, max_words, max_matches, result_queue):
    """Extraction, corpus reads and CPU comparison all stay inside the deadline.

    No results are committed here. Terminating this process cannot leave half
    of an index or matches behind; the parent seals both outcomes atomically.
    """
    engine = None
    try:
        extracted = extract_local_similarity_paragraphs(path, max_words=max_words)
        engine = create_database_engine(database_url, worker=True)
        with sessionmaker(bind=engine, autoflush=False, future=True)() as db:
            db.execute(text("SET TRANSACTION READ ONLY"))
            prepared = LocalPlagiarismService(db).prepare(
                job_id, worker_id, extracted, max_matches=max_matches,
            )
        result_queue.put(("success", prepared))
    except Exception as exc:
        capture_exception(exc)
        log.exception("local_similarity_child_failed", extra={"component": "document_check_worker"})
        result_queue.put(("error", "LOCAL_SIMILARITY_ANALYSIS_FAILED"))
    finally:
        if engine is not None:
            engine.dispose()


def _finding_from_dict(value: dict) -> AnalyzerFinding:
    from app.models.enums import CheckRuleSeverity, CheckRuleType
    import uuid
    return AnalyzerFinding(
        check_rule_id=uuid.UUID(value["check_rule_id"]), rule_type=CheckRuleType(value["rule_type"]),
        category=value["category"], severity=CheckRuleSeverity(value["severity"]),
        code=value["code"], property_name=value["property_name"], location=value["location"],
        expected=value["expected"], actual=value["actual"],
    )


class DocumentCheckWorker:
    def __init__(self, session_factory, *, worker_id: str | None = None, storage=None):
        self.session_factory = session_factory
        self.worker_id = (worker_id or default_worker_id())[:128]
        # Production storage clients are constructed inside the spawned child;
        # boto3 clients/connections must never be pickled across processes.
        self.storage = storage
        self.stopping = False

    @staticmethod
    def _stop(process) -> None:
        if process is not None and process.is_alive():
            process.terminate()
            process.join(timeout=2)
        if process is not None and process.is_alive():
            process.kill()
            process.join(timeout=2)

    def recover(self) -> int:
        with self.session_factory() as db:
            return DocumentCheckJobService(db).recover_stale()

    def _run_child(self, job_id, target, args):
        ctx = multiprocessing.get_context("spawn")
        result_queue = ctx.Queue(maxsize=1)
        process = ctx.Process(target=target, args=(*args, result_queue), daemon=False)
        deadline = time.monotonic() + settings.DOCUMENT_CHECK_WORKER_TIMEOUT_SECONDS
        heartbeat_interval = max(1.0, min(10.0, settings.DOCUMENT_CHECK_WORKER_LEASE_SECONDS / 3))
        next_heartbeat = time.monotonic()
        outcome = None
        try:
            if self.stopping:
                return ("error", "CHECK_WORKER_STOPPED")
            process.start()
            while process.is_alive():
                process.join(timeout=0.25)
                # Drain before joining fully: large queue messages otherwise
                # block the child's feeder thread and prevent process exit.
                if outcome is None:
                    try:
                        outcome = result_queue.get_nowait()
                    except queue.Empty:
                        pass
                if self.stopping:
                    return ("error", "CHECK_WORKER_STOPPED")
                if time.monotonic() >= deadline:
                    return ("error", "CHECK_ANALYSIS_TIMEOUT")
                if time.monotonic() >= next_heartbeat:
                    with self.session_factory() as db:
                        db.execute(text("SELECT set_config('statement_timeout', '2000', true)"))
                        db.execute(text("SELECT set_config('lock_timeout', '1000', true)"))
                        if not DocumentCheckJobService(db).heartbeat(job_id, self.worker_id):
                            raise _LeaseLost
                    next_heartbeat = time.monotonic() + heartbeat_interval
            process.join(timeout=1)
            if outcome is None:
                try:
                    outcome = result_queue.get(timeout=1)
                except queue.Empty:
                    return ("error", "CHECK_ANALYSIS_FAILED")
            return outcome
        finally:
            self._stop(process)
            result_queue.close()

    def _finish(self, job_id, findings, summary, prepared, has_similarity):
        with self.session_factory() as db:
            # Bound SQL/lock waits too. The job lock serializes finalization
            # with recovery; expensive analysis has already finished outside it.
            db.execute(text("SELECT set_config('statement_timeout', :value, true)"),
                       {"value": str(settings.DOCUMENT_CHECK_WORKER_TIMEOUT_SECONDS * 1000)})
            db.execute(text("SELECT set_config('lock_timeout', '5000', true)"))
            similarity = LocalPlagiarismService(db)
            if DocumentCheckJobService(db).lock_owned_job(job_id, self.worker_id) is None:
                return
            if has_similarity:
                if prepared is not None:
                    try:
                        with db.begin_nested():
                            similarity.complete_prepared(job_id, self.worker_id, prepared)
                    except Exception as exc:
                        # Roll back the entire partial similarity write, not the
                        # already computed formatting result or its job lease.
                        capture_exception(exc)
                        log.exception("local_similarity_persist_failed", extra={"component": "document_check_worker"})
                        similarity.fail_analysis(job_id, self.worker_id)
                else:
                    similarity.fail_analysis(job_id, self.worker_id)
            DocumentCheckJobService(db).complete(job_id, self.worker_id, findings, summary)

    def process_next(self) -> bool:
        with self.session_factory() as db:
            service = DocumentCheckJobService(db)
            job = service.claim_next(self.worker_id)
            if job is None:
                return False
            job_id = job.id
            LocalPlagiarismService(db).mark_processing(job)
            db.commit()
            payload = service.payload(job_id, self.worker_id)
            if payload is None:
                service.retry_or_fail(job_id, self.worker_id, "CHECK_ANALYSIS_FAILED")
                return True
            submission, rules = payload
            paragraph_overrides = (job.settings_snapshot or {}).get("paragraph_overrides", {})
            storage_key, expected_size, expected_sha = submission.storage_key, submission.size_bytes, submission.sha256
            has_similarity = job.teacher_submission_id is not None
            database_url = db.get_bind().url

        try:
            with tempfile.TemporaryDirectory(prefix="practiceflow-check-") as directory:
                path = Path(directory) / "original.docx"
                outcome = self._run_child(job_id, _stage_and_analyze_child, (
                    str(path), self.storage, storage_key, expected_size, expected_sha,
                    settings.DOCX_MAX_UPLOAD_BYTES, rules, settings.DOCUMENT_CHECK_MAX_FINDINGS, paragraph_overrides,
                ))
                if outcome[0] != "success":
                    self._retry(job_id, outcome[1])
                    return True
                findings = [_finding_from_dict(value) for value in outcome[1]]
                prepared = None
                if has_similarity:
                    try:
                        similarity_outcome = self._run_child(job_id, _similarity_child, (
                            str(path), database_url, job_id, self.worker_id,
                            settings.LOCAL_PLAGIARISM_MAX_INDEXED_WORDS, settings.LOCAL_PLAGIARISM_MAX_MATCHES,
                        ))
                        if similarity_outcome[0] == "success":
                            prepared = similarity_outcome[1]
                    except _LeaseLost:
                        raise
                    except Exception as exc:
                        capture_exception(exc)
                        log.exception("local_similarity_stage_failed", extra={"component": "document_check_worker"})
                self._finish(job_id, findings, outcome[2], prepared, has_similarity)
                return True
        except _LeaseLost:
            # Another worker owns recovery. Neither its run nor its failure
            # state may be overwritten by the old process.
            return True
        except Exception as exc:
            capture_exception(exc)
            log.exception("document_check_worker_job_failed", extra={"component": "document_check_worker"})
            self._retry(job_id, "CHECK_ANALYSIS_FAILED")
            return True

    def _retry(self, job_id, code: str) -> None:
        with self.session_factory() as db:
            DocumentCheckJobService(db).retry_or_fail(job_id, self.worker_id, code)

    def run_forever(self) -> None:
        self.recover()
        next_recovery = time.monotonic() + 30
        while not self.stopping:
            try:
                worked = self.process_next()
                if not worked:
                    time.sleep(settings.DOCUMENT_CHECK_WORKER_POLL_SECONDS)
                if time.monotonic() >= next_recovery:
                    self.recover()
                    next_recovery = time.monotonic() + 30
            except Exception as exc:
                capture_exception(exc)
                log.exception("document_check_worker_loop_failed", extra={"component": "document_check_worker"})
                time.sleep(settings.DOCUMENT_CHECK_WORKER_POLL_SECONDS)


def _healthcheck() -> int:
    try:
        engine = create_database_engine(worker=True)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        engine.dispose()
        return 0 if get_storage_service().ping() else 1
    except Exception:
        return 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        return _healthcheck()
    configure_structured_logging(settings.LOG_LEVEL)
    configure_error_tracking(settings.SENTRY_DSN, settings.SENTRY_ENVIRONMENT or settings.ENV)
    engine = create_database_engine(worker=True)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    worker = DocumentCheckWorker(factory)

    def stop(_signum, _frame):
        worker.stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    worker.run_forever()
    engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
