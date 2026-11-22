"""Real PostgreSQL/API regressions for immutable original DOCX submissions."""

import hashlib
import importlib.util
import io
import json
import struct
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.core.config import settings
from app.main import app
from app.models.audit_log import AuditLog
from app.models.document_check import (
    DocumentCheckFinding, DocumentCheckJob, TeacherDocumentSubmission,
)
from app.models.enums import AuditEventType, DocumentCheckJobStatus
from app.models.membership import OrganizationMembership
from app.models.student import Student
from app.models.teacher import Teacher
from app.models.user import User
from app.rate_limit.dependencies import get_resource_guard
from app.resource_protection import MemoryResourceGuard, ResourceProtectionConfig
from app.storage.local import LocalStorageService
from app.services.document_analyzer import analyze_document
from app.services.document_check_job_service import DocumentCheckJobService
from app.workers.document_check_worker import DocumentCheckWorker
from app.tests.conftest import TestSessionLocal, auth_headers, engine
from app.tests.test_document_check_phase1 import _create_published_profile

PREFIX = "/api/v1/document-checks"
MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    '</Types>'
)
RELS = (
    '<?xml version="1.0"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
    'officeDocument" Target="word/document.xml"/></Relationships>'
)


def docx_bytes(*, extra=None, omit=None, content_types=CONTENT_TYPES, body="Student original", title_page=False):
    title = '<w:p><w:r><w:t>Title page</w:t><w:br w:type="page"/></w:r></w:p>' if title_page else ""
    entries = {
        "[Content_Types].xml": content_types,
        "_rels/.rels": RELS,
        "word/document.xml": (
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f'<w:body>{title}<w:p><w:r><w:t>{body}</w:t></w:r></w:p></w:body></w:document>'
        ),
    }
    entries.update(extra or {})
    if omit:
        entries.pop(omit)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, value in entries.items():
            # Idempotent retry tests must send identical bytes, including ZIP
            # metadata, even when two uploads cross a two-second ZIP timestamp.
            info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, value)
    return output.getvalue()


def encrypted_zip_bytes():
    payload = bytearray(docx_bytes())
    # The flag must be inspected before attempting to inflate an entry. This
    # changes both directory and local headers without needing encryption keys.
    for signature, offset in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
        position = 0
        while (position := payload.find(signature, position)) >= 0:
            flags = struct.unpack_from("<H", payload, position + offset)[0]
            struct.pack_into("<H", payload, position + offset, flags | 1)
            position += 4
    return bytes(payload)


def _teacher_upload_for_rules(client, version_id, headers):
    response = client.post(f"{PREFIX}/teacher/submissions", headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
                           data={"profile_version_id": version_id},
                           files={"file": ("same-name.docx", docx_bytes(body="Введение", title_page=True), MIME)})
    assert response.status_code == 201, response.text
    return response.json()


def _saved_document_settings(client, path, headers, draft):
    payload = {key: draft[key] for key in ("revision", "rules", "paragraph_overrides", "page_exclusions")}
    response = client.put(f"{path}/settings", headers=headers, json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def test_document_settings_are_scoped_persistent_and_authorized(client, db, org_a, org_b, published):
    from app.models.document_check import CheckRule
    assignment, student_headers, headers = published
    before = [(str(rule.id), json.dumps(rule.config, sort_keys=True)) for rule in db.scalars(select(CheckRule).order_by(CheckRule.id))]
    first = _teacher_upload_for_rules(client, assignment["profile_version_id"], headers)
    second = _teacher_upload_for_rules(client, assignment["profile_version_id"], headers)
    path = f"{PREFIX}/teacher/submissions/{first['id']}"
    draft = client.get(f"{path}/settings", headers=headers).json()
    original_settings = json.loads(json.dumps(draft))
    draft["paragraph_overrides"] = {"2": "HEADING_2"}
    heading = next(rule for rule in draft["rules"] if rule["rule_type"] == "HEADINGS")
    heading["config"]["levels"][0]["alignment"] = "RIGHT"
    saved = _saved_document_settings(client, path, headers, draft)
    assert saved["revision"] == draft["revision"] + 1
    # A fresh session/login still reads the same document settings.
    db.expire_all()
    fresh_headers = auth_headers(org_a.teacher_token(client))
    assert client.get(f"{path}/settings", headers=fresh_headers).json() == saved
    untouched = client.get(f"{PREFIX}/teacher/submissions/{second['id']}/settings", headers=headers).json()
    assert untouched["paragraph_overrides"] == {} and untouched["rules"] == original_settings["rules"]
    assert before == [(str(rule.id), json.dumps(rule.config, sort_keys=True)) for rule in db.scalars(select(CheckRule).order_by(CheckRule.id))]
    for forbidden_headers in (student_headers, auth_headers(org_b.teacher_token(client))):
        expected = 403 if forbidden_headers == student_headers else 404
        for suffix in ("settings", "paragraphs", "runs"):
            assert client.get(f"{path}/{suffix}", headers=forbidden_headers).status_code == expected
        assert client.post(f"{path}/recheck", headers={**forbidden_headers, "Idempotency-Key": "blocked"}, json={"revision": saved["revision"]}).status_code == expected
    other_user, _ = _additional_actor(db, org_a, teacher=True)
    other_headers = auth_headers(org_a.login(client, other_user.email))
    assert client.get(f"{path}/settings", headers=other_headers).status_code == 404
    invalid = {key: saved[key] for key in ("revision", "rules", "paragraph_overrides")}
    invalid["paragraph_overrides"] = {"999": "BODY"}
    assert client.put(f"{path}/settings", headers=headers, json=invalid).status_code == 422
    stale = {key: original_settings[key] for key in ("revision", "rules", "paragraph_overrides")}
    assert client.put(f"{path}/settings", headers=headers, json=stale).status_code == 409


def test_rechecks_keep_snapshots_history_and_order_when_finishing_late(client, db, published, private_storage):
    from app.models.document_check import DocumentCheckRunRule
    assignment, _, headers = published
    uploaded = _teacher_upload_for_rules(client, assignment["profile_version_id"], headers)
    path = f"{PREFIX}/teacher/submissions/{uploaded['id']}"
    service = DocumentCheckJobService(db)
    old_job = service.claim_next("old-worker")
    old_id = old_job.id
    original_snapshot = json.loads(json.dumps(old_job.settings_snapshot))
    draft = client.get(f"{path}/settings", headers=headers).json()
    draft["paragraph_overrides"] = {"2": "BODY"}
    saved = _saved_document_settings(client, path, headers, draft)
    key = str(uuid.uuid4())
    queued = client.post(f"{path}/recheck", headers={**headers, "Idempotency-Key": key}, json={"revision": saved["revision"]})
    assert queued.status_code == 200, queued.text
    assert queued.json()["run_number"] == 2
    new_job = service.claim_next("new-worker")
    new_id = new_job.id
    # Saving while workers run must not change either in-flight snapshot.
    saved["paragraph_overrides"] = {"2": "HEADING_3"}
    _saved_document_settings(client, path, headers, saved)
    for job_id, worker, expected_overrides in ((new_id, "new-worker", {"2": "BODY"}), (old_id, "old-worker", {})):
        db.expire_all()
        job = db.get(DocumentCheckJob, job_id)
        assert job.settings_snapshot["paragraph_overrides"] == expected_overrides
        submission, rules = service.payload(job_id, worker)
        with private_storage.open(submission.storage_key) as source:
            findings, summary = analyze_document(source, rules, max_findings=5000, paragraph_overrides=expected_overrides)
        assert service.complete(job_id, worker, findings, summary)
    latest = client.get(path, headers=headers).json()
    assert latest["job"]["id"] == str(new_id)
    assert latest["latest_completed_job"]["id"] == str(new_id)
    history = client.get(f"{path}/runs", headers=headers).json()
    assert [item["run_number"] for item in history] == [2, 1]
    again = client.post(f"{path}/recheck", headers={**headers, "Idempotency-Key": key}, json={"revision": saved["revision"]})
    assert again.status_code == 200 and again.json()["id"] == str(new_id)
    assert db.scalar(select(func.count()).select_from(DocumentCheckJob)) == 2
    db.expire_all()
    assert db.get(DocumentCheckJob, old_id).settings_snapshot == original_snapshot
    for job_id in (old_id, new_id):
        result = client.get(f"{path}/findings?job_id={job_id}&limit=100", headers=headers)
        assert result.status_code == 200 and result.json()
        assert all(item["check_rule_id"] is None and item["run_rule_id"] for item in result.json())
    other = _teacher_upload_for_rules(client, assignment["profile_version_id"], headers)
    assert client.get(f"{path}/findings?job_id={other['job']['id']}", headers=headers).status_code == 404
    # Both ORM and SQL protections stay active for snapshots and terminal jobs.
    run_rule = db.scalar(select(DocumentCheckRunRule).where(DocumentCheckRunRule.job_id == old_id))
    run_rule_id = run_rule.id
    run_rule.config = {"changed": True}
    with pytest.raises(ValueError):
        db.flush()
    db.rollback()
    for sql, identity in (("UPDATE document_check_run_rules SET config = '{}' WHERE id = :id", run_rule_id),
                          ("UPDATE document_check_jobs SET settings_snapshot = '{}' WHERE id = :id", old_id)):
        with pytest.raises(DBAPIError):
            db.execute(text(sql), {"id": identity})
            db.commit()
        db.rollback()


def test_page_exclusions_work_with_forward_only_storage_and_reject_changed_originals(client, published, private_storage, monkeypatch):
    assignment, _, headers = published
    uploaded = _teacher_upload_for_rules(client, assignment["profile_version_id"], headers)
    path = f"{PREFIX}/teacher/submissions/{uploaded['id']}"
    # Production S3 streams support read/close, but not seek or context managers.
    from app.storage.s3 import _S3ObjectStream
    original_open = private_storage.open
    opened = []

    def streaming_open(key):
        stream = _S3ObjectStream(original_open(key))
        opened.append(stream)
        return stream

    monkeypatch.setattr(private_storage, "open", streaming_open)
    assert client.get(f"{path}/preview", headers=headers).status_code == 200
    assert client.get(f"{path}/paragraphs", headers=headers).status_code == 200
    draft = client.get(f"{path}/settings", headers=headers).json()
    draft["page_exclusions"] = {"pages": [2], "layout": [
        {"number": 1, "section_index": 1, "paragraphs": {"1": []}},
        {"number": 2, "section_index": 1, "paragraphs": {"2": [1]}},
    ]}
    assert _saved_document_settings(client, path, headers, draft)["page_exclusions"]["pages"] == [2]
    assert opened and all(stream._closed for stream in opened)
    corrupted = _S3ObjectStream(io.BytesIO(b"x" * uploaded["size_bytes"]))
    monkeypatch.setattr(private_storage, "open", lambda key: corrupted)
    assert client.get(f"{path}/preview", headers=headers).status_code == 422
    assert corrupted._closed


def test_page_exclusions_persist_in_worker_snapshot_and_can_be_removed(client, db, published, private_storage):
    assignment, _, headers = published
    uploaded = _teacher_upload_for_rules(client, assignment["profile_version_id"], headers)
    path = f"{PREFIX}/teacher/submissions/{uploaded['id']}"
    worker = DocumentCheckWorker(worker_id="page-exclusions-worker", storage=private_storage, session_factory=TestSessionLocal)
    assert worker.process_next()
    original_findings = client.get(f"{path}/findings", headers=headers).json()
    assert original_findings
    draft = client.get(f"{path}/settings", headers=headers).json()
    assert draft["page_exclusions"] == {"pages": [], "layout": []}
    draft["page_exclusions"] = {"pages": [2], "layout": [
        {"number": 1, "section_index": 1, "paragraphs": {"1": []}},
        {"number": 2, "section_index": 1, "paragraphs": {"2": [1]}},
    ]}
    saved = _saved_document_settings(client, path, headers, draft)
    assert saved["revision"] == 2
    assert client.get(f"{path}/settings", headers=headers).json() == saved
    # Identical retries are idempotent; a different stale exclusion conflicts.
    assert _saved_document_settings(client, path, headers, draft) == saved
    stale = {key: saved[key] for key in ("revision", "rules", "paragraph_overrides", "page_exclusions")}
    stale.update(revision=1, page_exclusions={})
    assert client.put(f"{path}/settings", headers=headers, json=stale).status_code == 409
    queued = client.post(f"{path}/recheck", headers={**headers, "Idempotency-Key": "exclude-page-two"}, json={"revision": 2})
    assert queued.status_code == 200
    run_id = queued.json()["id"]
    saved["page_exclusions"] = {"pages": [], "layout": []}
    _saved_document_settings(client, path, headers, saved)
    assert worker.process_next()
    detail = client.get(f"{path}/runs/{run_id}", headers=headers).json()
    assert detail["status"] == "COMPLETED"
    assert detail["page_exclusions"]["pages"] == [2]
    assert detail["result_summary"]["excluded_pages"] == [2]
    assert detail["result_summary"]["findings_count"] == 0
    old = client.get(f"{path}/findings?job_id={uploaded['job']['id']}", headers=headers).json()
    assert old == original_findings
    queued = client.post(f"{path}/recheck", headers={**headers, "Idempotency-Key": "restore-page-two"}, json={"revision": 3})
    assert queued.status_code == 200
    assert worker.process_next()
    assert client.get(f"{path}/findings", headers=headers).json()


def test_page_exclusion_map_rejects_unknown_or_missing_source_locations(client, published, private_storage):
    assignment, _, headers = published
    uploaded = _teacher_upload_for_rules(client, assignment["profile_version_id"], headers)
    path = f"{PREFIX}/teacher/submissions/{uploaded['id']}"
    draft = client.get(f"{path}/settings", headers=headers).json()
    payload = {key: draft[key] for key in ("revision", "rules", "paragraph_overrides")}
    for paragraphs in ({"999": [1]}, {"2": [999]}, {}):
        payload["page_exclusions"] = {"pages": [2], "layout": [
            {"number": 1, "section_index": 1, "paragraphs": {}},
            {"number": 2, "section_index": 1, "paragraphs": paragraphs},
        ]}
        assert client.put(f"{path}/settings", headers=headers, json=payload).status_code == 422
    assert client.get(f"{path}/settings", headers=headers).json()["revision"] == 1


def test_failed_recheck_preserves_last_result(client, db, published, private_storage, monkeypatch):
    assignment, _, headers = published
    uploaded = _teacher_upload_for_rules(client, assignment["profile_version_id"], headers)
    path = f"{PREFIX}/teacher/submissions/{uploaded['id']}"
    service = DocumentCheckJobService(db)
    first = service.claim_next("first-worker")
    first_id = first.id
    submission, rules = service.payload(first_id, "first-worker")
    with private_storage.open(submission.storage_key) as source:
        findings, summary = analyze_document(source, rules, max_findings=5000)
    assert service.complete(first_id, "first-worker", findings, summary)
    draft = client.get(f"{path}/settings", headers=headers).json()
    response = client.post(f"{path}/recheck", headers={**headers, "Idempotency-Key": "will-fail"}, json={"revision": draft["revision"]})
    assert response.status_code == 200
    second = service.claim_next("failed-worker")
    monkeypatch.setattr(settings, "DOCUMENT_CHECK_WORKER_MAX_ATTEMPTS", 1)
    service.retry_or_fail(second.id, "failed-worker", "CHECK_ANALYSIS_FAILED")
    result = client.get(path, headers=headers).json()
    assert result["job"]["status"] == "FAILED"
    assert result["latest_completed_job"]["id"] == str(first_id)
    assert client.get(f"{path}/findings", headers=headers).json()
    downloaded = client.get(f"{path}/original", headers=headers)
    assert hashlib.sha256(downloaded.content).hexdigest() == uploaded["sha256"]


@pytest.fixture(scope="module", autouse=True)
def phase21_database_guards(_create_schema):
    # The shared suite deliberately builds metadata directly. Install the same
    # production DDL here so SQL-level immutability tests exercise real triggers.
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            analyzer_path = Path(__file__).parents[2] / "alembic" / "versions" / "fb3a4b5c6d7e_document_check_analyzer_results.py"
            analyzer_spec = importlib.util.spec_from_file_location("phase22_migration_for_test", analyzer_path)
            analyzer_migration = importlib.util.module_from_spec(analyzer_spec)
            analyzer_spec.loader.exec_module(analyzer_migration)
            analyzer_migration.install_analyzer_guards()
            connection.execute(text(
                "CREATE TRIGGER trg_protect_check_job_identity BEFORE UPDATE OR DELETE ON document_check_jobs "
                "FOR EACH ROW EXECUTE FUNCTION pf_protect_check_job_identity()"
            ))
            teacher_path = Path(__file__).parents[2] / "alembic" / "versions" / "0c4d5e6f7a8b_teacher_only_document_checks.py"
            teacher_spec = importlib.util.spec_from_file_location("teacher_checks_migration_for_test", teacher_path)
            teacher_migration = importlib.util.module_from_spec(teacher_spec)
            teacher_spec.loader.exec_module(teacher_migration)
            teacher_migration.install_teacher_submission_guards()
            runs_path = Path(__file__).parents[2] / "alembic" / "versions" / "1d5e6f7a8b9c_document_settings_and_runs.py"
            runs_spec = importlib.util.spec_from_file_location("document_runs_migration_for_test", runs_path)
            runs_migration = importlib.util.module_from_spec(runs_spec)
            runs_spec.loader.exec_module(runs_migration)
            runs_migration.install_document_settings_guards()
    yield
    with engine.begin() as connection:
        for name in ("pf_protect_check_job_identity",
                     "pf_validate_document_check_finding", "pf_protect_teacher_original",
                     "pf_validate_teacher_submission", "pf_require_teacher_submission_job", "pf_protect_run_rule"):
            connection.execute(text(f"DROP FUNCTION IF EXISTS {name}() CASCADE"))


@pytest.fixture(autouse=True)
def private_storage(tmp_path, monkeypatch, client):
    from app.services import teacher_document_submission_service

    storage = LocalStorageService(str(tmp_path / "originals"))
    monkeypatch.setattr(teacher_document_submission_service, "get_storage_service", lambda: storage)
    monkeypatch.setattr(settings, "DOCUMENT_CHECK_ENABLED", True)
    guard = MemoryResourceGuard(ResourceProtectionConfig.from_settings(settings))
    app.dependency_overrides[get_resource_guard] = lambda: guard
    return storage


@pytest.fixture
def published(client, org_a):
    _, version = _create_published_profile(client, org_a, name=f"Profile {uuid.uuid4()}")
    return (
        {"profile_version_id": version["id"]},
        auth_headers(org_a.student_token(client)),
        auth_headers(org_a.teacher_token(client)),
    )


def _upload(client, version_holder, headers, payload=None, *, filename="original.docx", key=None):
    return client.post(
        f"{PREFIX}/teacher/submissions",
        headers={**headers, "Idempotency-Key": key or str(uuid.uuid4())},
        data={"profile_version_id": version_holder["profile_version_id"]},
        files={"file": (filename, payload if payload is not None else docx_bytes(), MIME)},
    )


def _counts(db):
    return (
        db.scalar(select(func.count()).select_from(TeacherDocumentSubmission)),
        db.scalar(select(func.count()).select_from(DocumentCheckJob)),
    )


def _files(storage):
    return sorted(path for path in storage.root.rglob("*") if path.is_file())


def _additional_actor(db, fixture, *, teacher=False):
    user = User(
        email=f"additional-{uuid.uuid4()}@{fixture.org.slug}.edu",
        full_name="Another member", hashed_password=fixture.student_user.hashed_password,
    )
    db.add(user)
    db.flush()
    membership = OrganizationMembership(
        organization_id=fixture.org.id, user_id=user.id,
        role_id=fixture.role_teacher.id if teacher else fixture.role_student.id,
    )
    db.add(membership)
    db.flush()
    actor = Teacher(membership_id=membership.id) if teacher else Student(membership_id=membership.id)
    db.add(actor)
    db.commit()
    return user, actor


def test_direct_sql_cannot_delete_original_or_job(client, db, published):
    version_holder, _, headers = published
    response = _upload(client, version_holder, headers)
    assert response.status_code == 201, response.text
    for table in ("teacher_document_submissions", "document_check_jobs"):
        with pytest.raises(DBAPIError):
            db.execute(text(f"DELETE FROM {table}"))
            db.commit()
        db.rollback()
    with pytest.raises(DBAPIError):
        db.execute(text("UPDATE document_check_jobs SET teacher_submission_id = :id"), {"id": uuid.uuid4()})
        db.commit()
    db.rollback()
    assert _counts(db) == (1, 1)


def test_request_rate_and_envelope_limits_leave_no_artifacts(client, db, published, private_storage, monkeypatch):
    version_holder, _, headers = published
    guard = MemoryResourceGuard(replace(ResourceProtectionConfig.from_settings(settings), upload_rate_requests=1))
    app.dependency_overrides[get_resource_guard] = lambda: guard
    assert _upload(client, version_holder, headers, b"not DOCX").status_code == 400
    assert _upload(client, version_holder, headers).status_code == 429
    monkeypatch.setattr(settings, "DOCX_MAX_UPLOAD_BYTES", 1)
    envelope = _upload(client, version_holder, headers, b"X" * 70_000)
    assert envelope.status_code == 413
    assert envelope.json()["detail"]["code"] == "DOCX_UPLOAD_TOO_LARGE"
    assert _counts(db) == (0, 0)
    assert _files(private_storage) == []


def test_openapi_exposes_teacher_only_read_only_original_and_multipart_idempotency():
    schema = app.openapi()
    paths = schema["paths"]
    upload_path = f"{PREFIX}/teacher/submissions"
    original_path = f"{PREFIX}/teacher/submissions/{{submission_id}}/original"
    assert "post" in paths[upload_path]
    upload = paths[upload_path]["post"]
    assert "multipart/form-data" in upload["requestBody"]["content"]
    assert any(parameter["name"].lower() == "idempotency-key" for parameter in upload["parameters"])
    assert set(paths[original_path]) == {"get", "delete"}  # retention endpoint; no replacement
    assert f"{PREFIX}/student/assignments" not in paths
    for path, operations in paths.items():
        if path.startswith(PREFIX) and "submissions" in path:
            assert "patch" not in operations
            if "delete" in operations:
                assert path == original_path
            if "put" in operations:
                assert path in {f"{PREFIX}/teacher/submissions/{{submission_id}}/{suffix}" for suffix in ("settings", "lifecycle", "review")}
    response = upload["responses"]["201"]["content"]["application/json"]["schema"]
    properties = schema["components"]["schemas"][response["$ref"].rsplit("/", 1)[1]]["properties"]
    assert {"profile_version_id", "student_label", "sha256", "submitted_at", "job",
            "review_group_id", "work_title", "work_type", "teacher_review"} <= properties.keys()
    assert "storage_key" not in properties
    assert "grade" not in properties


def test_worker_claims_are_exclusive_and_failures_are_bounded(client, db, published, monkeypatch):
    assignment, _, headers = published
    assert _upload(client, assignment, headers).status_code == 201
    assert _upload(client, assignment, headers, docx_bytes(body="second")).status_code == 201
    db.commit()

    barrier = Barrier(2)
    def claim(worker):
        with TestSessionLocal() as session:
            barrier.wait(timeout=10)
            job = DocumentCheckJobService(session).claim_next(worker)
            return job.id if job else None

    with ThreadPoolExecutor(max_workers=2) as pool:
        claimed = list(pool.map(claim, ("worker-a", "worker-b")))
    assert None not in claimed
    assert len(set(claimed)) == 2

    monkeypatch.setattr(settings, "DOCUMENT_CHECK_WORKER_MAX_ATTEMPTS", 1)
    with TestSessionLocal() as session:
        job = session.get(DocumentCheckJob, claimed[0])
        status = DocumentCheckJobService(session).retry_or_fail(job.id, job.worker_id, "INTERNAL_SECRET_ERROR")
        assert status == DocumentCheckJobStatus.FAILED
    db.expire_all()
    failed = db.get(DocumentCheckJob, claimed[0])
    assert failed.error_code == "CHECK_ANALYSIS_FAILED"
    assert "INTERNAL" not in failed.error_message


def test_independent_worker_checks_exact_stored_original(client, db, published, private_storage, tmp_path, monkeypatch):
    assignment, _, headers = published
    original = docx_bytes(body="Worker reads this original without modifying it", title_page=True)
    accepted = _upload(client, assignment, headers, original)
    assert accepted.status_code == 201, accepted.text
    db.commit()
    # Keep the spawned analyzer's private temporary copy inside pytest's
    # writable test directory on Windows CI.
    from app.workers import document_check_worker
    original_temporary_directory = document_check_worker.tempfile.TemporaryDirectory
    monkeypatch.setattr(
        document_check_worker.tempfile,
        "TemporaryDirectory",
        lambda **kwargs: original_temporary_directory(dir=tmp_path, **kwargs),
    )
    worker = DocumentCheckWorker(TestSessionLocal, worker_id="phase22-test-worker", storage=private_storage)
    assert worker.process_next() is True

    db.expire_all()
    job = db.scalar(select(DocumentCheckJob))
    assert job.status == DocumentCheckJobStatus.COMPLETED
    assert job.result_summary["rules_evaluated"] == 2
    submission = db.scalar(select(TeacherDocumentSubmission))
    assert private_storage.get(submission.storage_key) == original


@pytest.mark.parametrize("failure", ["analysis", "timeout", "stopped", "crash", "persistence", None])
def test_similarity_failure_cannot_discard_formatting_result(
    client, db, published, private_storage, monkeypatch, failure,
):
    from queue import SimpleQueue
    from app.models.document_check import LocalPlagiarismIndex, LocalPlagiarismRun
    from app.services.local_plagiarism_service import LocalPlagiarismService, extract_local_similarity_paragraphs
    from app.workers import document_check_worker as module

    assignment, _, headers = published
    uploaded = _teacher_upload_for_rules(client, assignment["profile_version_id"], headers)
    job_id = uuid.UUID(uploaded["job"]["id"])
    db.commit()
    stages = []

    def stage(worker, identity, target, args):
        stages.append(target)
        if target is module._stage_and_analyze_child:
            result = SimpleQueue()
            target(*args, result)
            return result.get_nowait()
        if failure in {"analysis", "timeout", "stopped"}:
            return ("error", {"analysis": "LOCAL_SIMILARITY_ANALYSIS_FAILED",
                              "timeout": "CHECK_ANALYSIS_TIMEOUT", "stopped": "CHECK_WORKER_STOPPED"}[failure])
        if failure == "crash":
            raise RuntimeError("Simulated process start failure")
        extracted = extract_local_similarity_paragraphs(args[0], max_words=1000)
        with TestSessionLocal() as session:
            prepared = LocalPlagiarismService(session).prepare(identity, worker.worker_id, extracted)
            # The expensive stage must not create an index or seal a result.
            assert session.scalar(select(func.count()).select_from(LocalPlagiarismIndex)) == 0
        return ("success", prepared)

    if failure == "persistence":
        original_complete = LocalPlagiarismService.complete_prepared

        def fail_after_writes(service, *args):
            original_complete(service, *args)
            # A database failure after index/match/audit writes must roll back
            # to the savepoint before the safe failure result is recorded.
            service.db.execute(text("SELECT 1 / 0"))

        monkeypatch.setattr(LocalPlagiarismService, "complete_prepared", fail_after_writes)
    monkeypatch.setattr(DocumentCheckWorker, "_run_child", stage)
    assert DocumentCheckWorker(TestSessionLocal, storage=private_storage).process_next()
    assert stages == [module._stage_and_analyze_child, module._similarity_child]
    db.expire_all()
    job = db.get(DocumentCheckJob, job_id)
    assert job.status == DocumentCheckJobStatus.COMPLETED
    assert job.attempt_count == 1 and job.error_code is None
    assert job.result_summary["findings_count"] > 0
    assert db.scalar(select(func.count()).select_from(DocumentCheckFinding).where(
        DocumentCheckFinding.job_id == job_id,
    )) == job.result_summary["findings_count"]
    similarity = db.scalar(select(LocalPlagiarismRun).where(LocalPlagiarismRun.job_id == job_id))
    assert similarity.status == (DocumentCheckJobStatus.FAILED if failure else DocumentCheckJobStatus.COMPLETED)
    assert db.scalar(select(func.count()).select_from(LocalPlagiarismIndex)) == (0 if failure else 1)
    if failure:
        assert similarity.error_code == "LOCAL_SIMILARITY_ANALYSIS_FAILED"
        assert db.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.event_type == AuditEventType.LOCAL_PLAGIARISM_RUN_COMPLETED,
        )) == 0


def test_expired_worker_cannot_renew_lease_or_fail_similarity(client, db, published, private_storage):
    from app.models.document_check import LocalPlagiarismRun
    from app.services.local_plagiarism_service import LocalPlagiarismService

    assignment, _, headers = published
    uploaded = _teacher_upload_for_rules(client, assignment["profile_version_id"], headers)
    service = DocumentCheckJobService(db)
    job = service.claim_next("expired-worker")
    job_id = job.id
    LocalPlagiarismService(db).mark_processing(job)
    job.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    assert service.heartbeat(job_id, "expired-worker") is False
    LocalPlagiarismService(db).fail_analysis(job_id, "expired-worker")
    db.commit()
    assert db.scalar(select(LocalPlagiarismRun.status).where(
        LocalPlagiarismRun.job_id == job_id,
    )) == DocumentCheckJobStatus.PROCESSING
    assert service.recover_stale() == 1
    replacement = service.claim_next("replacement-worker")
    assert str(replacement.id) == uploaded["job"]["id"]
    LocalPlagiarismService(db).mark_processing(replacement)
    db.commit()
    LocalPlagiarismService(db).fail_analysis(job_id, "expired-worker")
    db.commit()
    assert db.scalar(select(LocalPlagiarismRun.status).where(
        LocalPlagiarismRun.job_id == job_id,
    )) == DocumentCheckJobStatus.PROCESSING


def test_teacher_worker_completes_both_spawned_stages(client, db, published, private_storage):
    from app.models.document_check import LocalPlagiarismRun

    assignment, _, headers = published
    uploaded = _teacher_upload_for_rules(client, assignment["profile_version_id"], headers)
    db.commit()
    assert DocumentCheckWorker(TestSessionLocal, storage=private_storage).process_next()
    db.expire_all()
    job_id = uuid.UUID(uploaded["job"]["id"])
    assert db.get(DocumentCheckJob, job_id).status == DocumentCheckJobStatus.COMPLETED
    assert db.scalar(select(LocalPlagiarismRun.status).where(
        LocalPlagiarismRun.job_id == job_id,
    )) == DocumentCheckJobStatus.COMPLETED


def test_expired_worker_lease_is_requeued_without_losing_attempt_history(client, db, published):
    assignment, _, headers = published
    assert _upload(client, assignment, headers).status_code == 201
    service = DocumentCheckJobService(db)
    job = service.claim_next("crashed-worker")
    job.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()

    assert service.recover_stale() == 1
    db.expire_all()
    recovered = db.get(DocumentCheckJob, job.id)
    assert recovered.status == DocumentCheckJobStatus.QUEUED
    assert recovered.attempt_count == 1
    assert recovered.started_at is None
    claimed_again = service.claim_next("replacement-worker")
    assert claimed_again.id == job.id
    assert claimed_again.attempt_count == 2


def test_worker_hard_timeout_stops_child_and_persists_only_safe_error(
    client, db, published, private_storage, tmp_path, monkeypatch,
):
    assignment, _, headers = published
    assert _upload(client, assignment, headers).status_code == 201
    db.commit()

    class FakeQueue:
        def get_nowait(self):
            raise __import__("queue").Empty
        def get(self, timeout=None):
            raise __import__("queue").Empty
        def close(self):
            pass

    class HungProcess:
        alive = False
        terminated = False
        def __init__(self, **_kwargs):
            pass
        def start(self):
            self.alive = True
        def is_alive(self):
            return self.alive
        def join(self, timeout=None):
            if timeout:
                __import__("time").sleep(timeout)
        def terminate(self):
            self.terminated = True
            self.alive = False
        def kill(self):
            self.alive = False

    class FakeContext:
        process = None
        def Queue(self, maxsize=0):
            return FakeQueue()
        def Process(self, **kwargs):
            self.process = HungProcess(**kwargs)
            return self.process

    from app.workers import document_check_worker
    context = FakeContext()
    monkeypatch.setattr(document_check_worker.multiprocessing, "get_context", lambda _kind: context)
    real_temporary_directory = document_check_worker.tempfile.TemporaryDirectory
    monkeypatch.setattr(
        document_check_worker.tempfile,
        "TemporaryDirectory",
        lambda **kwargs: real_temporary_directory(dir=tmp_path, **kwargs),
    )
    monkeypatch.setattr(settings, "DOCUMENT_CHECK_WORKER_TIMEOUT_SECONDS", 1)
    monkeypatch.setattr(settings, "DOCUMENT_CHECK_WORKER_MAX_ATTEMPTS", 1)

    assert DocumentCheckWorker(TestSessionLocal, storage=private_storage).process_next() is True
    assert context.process.terminated is True
    db.expire_all()
    job = db.scalar(select(DocumentCheckJob))
    assert job.status == DocumentCheckJobStatus.FAILED
    assert job.error_code == "CHECK_ANALYSIS_TIMEOUT"
    assert "Traceback" not in job.error_message


def test_teacher_can_upload_and_check_without_student_account(
    client, db, org_a, org_b, published, private_storage, monkeypatch,
):
    assignment, student_headers, teacher_headers = published
    profile_version_id = assignment["profile_version_id"]
    original = docx_bytes(body="Teacher-owned document content", title_page=True)
    key = str(uuid.uuid4())

    def upload():
        return client.post(
            f"{PREFIX}/teacher/submissions",
            headers={**teacher_headers, "Idempotency-Key": key},
            data={"profile_version_id": profile_version_id, "student_label": "Student A"},
            files={"file": ("student-a.docx", original, MIME)},
        )

    accepted = upload()
    assert accepted.status_code == 201, accepted.text
    retry = upload()
    assert retry.status_code == 200, retry.text
    assert retry.json()["id"] == accepted.json()["id"]
    submission_id = uuid.UUID(accepted.json()["id"])
    assert accepted.json()["student_label"] == "Student A"
    assert accepted.json()["job"]["status"] == "QUEUED"
    assert "teacher_id" not in accepted.json()
    assert "storage_key" not in accepted.json()
    assert db.scalar(select(func.count()).select_from(TeacherDocumentSubmission)) == 1
    assert db.scalar(select(func.count()).select_from(DocumentCheckJob)) == 1

    assert client.get(f"{PREFIX}/teacher/submissions", headers=student_headers).status_code == 403
    other_teacher_user, _ = _additional_actor(db, org_a, teacher=True)
    other_teacher_headers = auth_headers(org_a.login(client, other_teacher_user.email))
    assert client.get(f"{PREFIX}/teacher/submissions", headers=other_teacher_headers).json() == []
    assert client.get(
        f"{PREFIX}/teacher/submissions/{submission_id}", headers=other_teacher_headers,
    ).status_code == 404
    other_tenant = auth_headers(org_b.teacher_token(client))
    assert client.get(
        f"{PREFIX}/teacher/submissions/{submission_id}", headers=other_tenant,
    ).status_code == 404

    service = DocumentCheckJobService(db)
    job = service.claim_next("teacher-check-worker")
    assert job is not None and job.teacher_submission_id == submission_id
    submission, rules = service.payload(job.id, "teacher-check-worker")
    assert isinstance(submission, TeacherDocumentSubmission)
    with private_storage.open(submission.storage_key) as source:
        findings, summary = analyze_document(source, rules, max_findings=5000)
    assert service.complete(job.id, "teacher-check-worker-bottom", findings, summary) is False
    assert service.complete(job.id, "teacher-check-worker", findings, summary) is True

    result = client.get(f"{PREFIX}/teacher/submissions/{submission_id}", headers=teacher_headers)
    assert result.status_code == 200, result.text
    assert result.json()["job"]["status"] == "COMPLETED"
    findings_response = client.get(
        f"{PREFIX}/teacher/submissions/{submission_id}/findings", headers=teacher_headers,
    )
    assert findings_response.status_code == 200, findings_response.text
    assert "Teacher-owned document content" not in findings_response.text
    downloaded = client.get(
        f"{PREFIX}/teacher/submissions/{submission_id}/original", headers=teacher_headers,
    )
    assert downloaded.status_code == 200
    assert hashlib.sha256(downloaded.content).digest() == hashlib.sha256(original).digest()

    with pytest.raises(DBAPIError):
        db.execute(text(
            "UPDATE teacher_document_submissions SET student_label = 'Changed' WHERE id = :id"
        ), {"id": submission_id})
        db.commit()
    db.rollback()
