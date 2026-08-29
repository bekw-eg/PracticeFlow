import queue
import uuid
from datetime import date, timedelta

from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.export_queue import MemoryExportQueue
from app.models.enums import ExportFormat, ExportJobStatus
from app.models.export_job import ExportJob
from app.models.internship import Internship
from app.models.report import Report
from app.resource_protection import MemoryResourceGuard, ResourceProtectionConfig
from app.services.export_job_service import ExportJobService, utcnow
from app.tests.conftest import OrgFixture
from app.workers.export_worker import ExportWorker


def _job(db, org: OrgFixture, **changes) -> ExportJob:
    internship = Internship(
        organization_id=org.org.id,
        group_id=org.group.id,
        template_version_id=org.template_version.id,
        created_by_teacher_id=org.teacher.id,
        title="Worker test internship",
        start_date=date.today(),
        end_date=date.today(),
        deadline=date.today(),
    )
    db.add(internship)
    db.flush()
    report = Report(organization_id=org.org.id, internship_id=internship.id, student_id=org.student.id)
    db.add(report)
    db.flush()
    values = {
        "organization_id": org.org.id,
        "report_id": report.id,
        "requested_by_user_id": org.student_user.id,
        "requested_role": "STUDENT",
        "format": ExportFormat.DOCX,
        "status": ExportJobStatus.QUEUED,
        "dedupe_key": f"report:{uuid.uuid4()}:docx",
        "expires_at": utcnow() + timedelta(hours=1),
    }
    values.update(changes)
    return ExportJob(**values)


class _NeverEndingProcess:
    def __init__(self, *_args, **_kwargs):
        self.alive = True

    def start(self):
        return None

    def is_alive(self):
        return self.alive

    def join(self, timeout=None):
        return None

    def terminate(self):
        self.alive = False

    def kill(self):
        self.alive = False


class _ExitedProcess(_NeverEndingProcess):
    def __init__(self, *_args, **_kwargs):
        self.alive = False


class _FakeContext:
    def __init__(self, process_type):
        self.process_type = process_type

    def Process(self, *args, **kwargs):
        return self.process_type(*args, **kwargs)

    @staticmethod
    def Queue(maxsize=0):
        class ClosableQueue(queue.Queue):
            def close(self):
                return None

        return ClosableQueue(maxsize=maxsize)


def _worker(db, queue_backend, guard):
    return ExportWorker(sessionmaker(bind=db.get_bind(), autoflush=False, autocommit=False, future=True), queue_backend, guard, "test-worker")


def test_worker_timeout_kills_renderer_and_releases_slot(db, org_a: OrgFixture, monkeypatch):
    import app.workers.export_worker as worker_module

    job = _job(db, org_a)
    db.add(job)
    db.commit()
    guard = MemoryResourceGuard(ResourceProtectionConfig.from_settings(settings))
    worker = _worker(db, MemoryExportQueue(), guard)
    monkeypatch.setattr(settings, "EXPORT_WORKER_HARD_TIMEOUT_SECONDS", 0)
    monkeypatch.setattr(worker_module.multiprocessing, "get_context", lambda _name: _FakeContext(_NeverEndingProcess))

    worker.process_job(str(job.id))
    db.expire_all()
    assert db.get(ExportJob, job.id).status == ExportJobStatus.TIMED_OUT
    # If finally failed to run, this second lease would return HTTP 429.
    replacement = guard.acquire_export_slot(org_a.org.id, org_a.student_user.id)
    guard.release_export(replacement)


def test_worker_failure_marks_terminal_and_releases_slot(db, org_a: OrgFixture, monkeypatch):
    import app.workers.export_worker as worker_module

    job = _job(db, org_a)
    db.add(job)
    db.commit()
    guard = MemoryResourceGuard(ResourceProtectionConfig.from_settings(settings))
    worker = _worker(db, MemoryExportQueue(), guard)
    monkeypatch.setattr(worker_module.multiprocessing, "get_context", lambda _name: _FakeContext(_ExitedProcess))

    worker.process_job(str(job.id))
    db.expire_all()
    assert db.get(ExportJob, job.id).status == ExportJobStatus.FAILED
    replacement = guard.acquire_export_slot(org_a.org.id, org_a.student_user.id)
    guard.release_export(replacement)


def test_recover_stale_worker_job_requeues_it(db, org_a: OrgFixture):
    queue_backend = MemoryExportQueue()
    job = _job(
        db,
        org_a,
        status=ExportJobStatus.RUNNING,
        worker_id="dead-worker",
        lease_expires_at=utcnow() - timedelta(seconds=1),
        started_at=utcnow() - timedelta(seconds=2),
    )
    db.add(job)
    db.commit()

    assert ExportJobService(db).recover_stale(queue_backend) == 1
    db.expire_all()
    assert db.get(ExportJob, job.id).status == ExportJobStatus.QUEUED
    assert queue_backend.dequeue(0) == str(job.id)


def test_cleanup_removes_expired_artifact_and_ledger_row(db, org_a: OrgFixture):
    job = _job(
        db,
        org_a,
        status=ExportJobStatus.SUCCEEDED,
        storage_key="orgs/test/exports/expired.docx",
        expires_at=utcnow() - timedelta(seconds=1),
    )
    db.add(job)
    db.commit()
    deleted: list[str] = []
    service = ExportJobService(db)
    service.storage = type("Storage", (), {"delete": lambda _self, key: deleted.append(key)})()

    assert service.cleanup_expired() == 1
    assert deleted == ["orgs/test/exports/expired.docx"]
    assert db.get(ExportJob, job.id) is None
