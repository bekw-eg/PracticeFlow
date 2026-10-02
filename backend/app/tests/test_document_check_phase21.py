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
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models.audit_log import AuditLog
from app.models.document_check import (
    AssignmentStudent, DocumentCheckFinding, DocumentCheckJob, StudentDocumentSubmission,
    TeacherDocumentSubmission,
)
from app.models.enums import AuditEventType, DocumentCheckJobStatus
from app.models.group_member import GroupMember
from app.models.membership import OrganizationMembership
from app.models.student import Student
from app.models.teacher import Teacher
from app.models.teacher_group import TeacherGroup
from app.models.user import User
from app.rate_limit.dependencies import get_resource_guard
from app.resource_protection import MemoryResourceGuard, ResourceProtectionConfig
from app.storage.base import StorageUnavailableError
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
    payload = {key: draft[key] for key in ("revision", "rules", "paragraph_overrides")}
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
    path = Path(__file__).parents[2] / "alembic" / "versions" / "ea2f3a4b5c6d_immutable_docx_submissions.py"
    spec = importlib.util.spec_from_file_location("phase21_migration_for_test", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration.install_guards()
            analyzer_path = Path(__file__).parents[2] / "alembic" / "versions" / "fb3a4b5c6d7e_document_check_analyzer_results.py"
            analyzer_spec = importlib.util.spec_from_file_location("phase22_migration_for_test", analyzer_path)
            analyzer_migration = importlib.util.module_from_spec(analyzer_spec)
            analyzer_spec.loader.exec_module(analyzer_migration)
            analyzer_migration.install_analyzer_guards()
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
        for name in ("pf_protect_student_original", "pf_validate_student_submission",
                     "pf_require_submission_job", "pf_protect_check_job_identity",
                     "pf_validate_document_check_finding", "pf_protect_teacher_original",
                     "pf_validate_teacher_submission", "pf_require_teacher_submission_job", "pf_protect_run_rule"):
            connection.execute(text(f"DROP FUNCTION IF EXISTS {name}() CASCADE"))


@pytest.fixture(autouse=True)
def private_storage(tmp_path, monkeypatch, client):
    from app.services import document_submission_service, teacher_document_submission_service

    storage = LocalStorageService(str(tmp_path / "originals"))
    monkeypatch.setattr(document_submission_service, "get_storage_service", lambda: storage)
    monkeypatch.setattr(teacher_document_submission_service, "get_storage_service", lambda: storage)
    monkeypatch.setattr(settings, "DOCUMENT_CHECK_ENABLED", True)
    monkeypatch.setattr(settings, "DOCUMENT_CHECK_STUDENT_SUBMISSIONS_ENABLED", True)
    guard = MemoryResourceGuard(ResourceProtectionConfig.from_settings(settings))
    app.dependency_overrides[get_resource_guard] = lambda: guard
    return storage


def _assignment(client, db, fixture, *, state="PUBLISHED", due_at=None):
    if db.scalar(select(GroupMember).where(
        GroupMember.group_id == fixture.group.id, GroupMember.student_id == fixture.student.id
    )) is None:
        db.add(GroupMember(group_id=fixture.group.id, student_id=fixture.student.id))
        db.commit()
    _, version = _create_published_profile(client, fixture, name=f"Profile {uuid.uuid4()}")
    headers = auth_headers(fixture.teacher_token(client))
    response = client.post(
        f"/api/v1/groups/{fixture.group.id}/check-assignments", headers=headers,
        json={
            "title": "Immutable DOCX",
            "profile_version_id": version["id"],
            "due_at": (due_at or datetime.now(UTC) + timedelta(days=1)).isoformat(),
            "assignment_timezone": "Asia/Qyzylorda",
        },
    )
    assert response.status_code == 201, response.text
    assignment = response.json()
    if state != "DRAFT":
        response = client.post(
            f"/api/v1/groups/{fixture.group.id}/check-assignments/{assignment['id']}/publish", headers=headers
        )
        assert response.status_code == 200, response.text
        assignment = response.json()
    if state == "CLOSED":
        response = client.post(
            f"/api/v1/groups/{fixture.group.id}/check-assignments/{assignment['id']}/close", headers=headers
        )
        assert response.status_code == 200, response.text
        assignment = response.json()
    return assignment, headers


@pytest.fixture
def published(client, db, org_a):
    assignment, teacher_headers = _assignment(client, db, org_a)
    return assignment, auth_headers(org_a.student_token(client)), teacher_headers


def _upload(client, assignment, headers, payload=None, *, filename="original.docx", key=None):
    return client.post(
        f"{PREFIX}/student/assignments/{assignment['id']}/submissions",
        headers={**headers, "Idempotency-Key": key or str(uuid.uuid4())},
        files={"file": (filename, payload if payload is not None else docx_bytes(), MIME)},
    )


def _counts(db):
    return (
        db.scalar(select(func.count()).select_from(StudentDocumentSubmission)),
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


def test_upload_download_exact_original_one_queued_job_and_safe_audit(client, db, org_a, published, private_storage):
    assignment, student_headers, teacher_headers = published
    original = docx_bytes(body="Original must never be transformed")
    response = _upload(client, assignment, student_headers, original, filename="Отчёт.docx")
    assert response.status_code == 201, response.text
    submission = response.json()
    assert submission["attempt_number"] == 1
    assert submission["sha256"] == hashlib.sha256(original).hexdigest()
    assert submission["size_bytes"] == len(original)
    assert submission["is_late"] is False
    assert submission["job"]["status"] == "QUEUED"
    assert submission["job"]["started_at"] is None
    assert submission["job"]["finished_at"] is None
    assert "storage_key" not in json.dumps(submission)
    assert _counts(db) == (1, 1)
    for headers in (student_headers, teacher_headers):
        download = client.get(f"{PREFIX}/submissions/{submission['id']}/original", headers=headers)
        assert download.status_code == 200, download.text
        assert download.content == original
        assert hashlib.sha256(download.content).hexdigest() == submission["sha256"]
        assert download.headers["content-disposition"].startswith("attachment;")
        assert "filename*=" in download.headers["content-disposition"]
    row = db.scalar(select(StudentDocumentSubmission))
    assert str(org_a.org.id) in row.storage_key
    assert assignment["id"] in row.storage_key
    assert str(row.id) in row.storage_key
    assert row.sha256 in row.storage_key
    assert _files(private_storage)[0].read_bytes() == original
    audits = db.scalars(select(AuditLog)).all()
    events = {event.event_type.value for event in audits}
    assert "DOCUMENT_CHECK_JOB_CREATED" in events
    assert any("SUBMISSION" in event and "UPLOAD" in event for event in events)
    assert any("DOWNLOAD" in event and "STUDENT" in event for event in events)
    assert any("DOWNLOAD" in event and "TEACHER" in event for event in events)
    metadata = json.dumps([event.event_metadata for event in audits])
    assert row.storage_key not in metadata
    assert "Original must never be transformed" not in metadata


def test_attempt_history_pagination_and_idempotent_retry(client, db, published, private_storage):
    assignment, headers, teacher_headers = published
    key = str(uuid.uuid4())
    first = _upload(client, assignment, headers, key=key)
    retry = _upload(client, assignment, headers, key=key)
    assert first.status_code == 201, first.text
    assert retry.status_code in (200, 201), retry.text
    assert first.json()["id"] == retry.json()["id"]
    assert _counts(db) == (1, 1)
    assert len(_files(private_storage)) == 1
    mismatch = _upload(client, assignment, headers, docx_bytes(body="Different original"), key=key)
    assert mismatch.status_code == 409, mismatch.text
    second = _upload(client, assignment, headers, docx_bytes(body="New attempt"))
    assert second.status_code == 201, second.text
    assert second.json()["attempt_number"] == 2
    assert _counts(db) == (2, 2)
    assert len(_files(private_storage)) == 2
    history = client.get(
        f"{PREFIX}/student/assignments/{assignment['id']}/submissions?limit=1", headers=headers
    )
    assert history.status_code == 200
    assert len(history.json()) == 1
    assert history.headers["x-total-count"] == "2"
    assert history.headers["x-has-more"] == "true"
    teacher_history = client.get(f"{PREFIX}/assignments/{assignment['id']}/submissions", headers=teacher_headers)
    assert teacher_history.status_code == 200, teacher_history.text
    assert sorted(item["attempt_number"] for item in teacher_history.json()) == [1, 2]


@pytest.mark.parametrize("same_key", [False, True], ids=["distinct-attempts", "idempotent-race"])
def test_concurrent_attempt_numbers_and_idempotency(client, db, published, same_key):
    assignment, headers, _ = published
    db.commit()

    def independent_session():
        with TestSessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = independent_session
    barrier = Barrier(3)
    key = str(uuid.uuid4())

    def submit(_):
        barrier.wait(timeout=10)
        return _upload(client, assignment, headers, key=key if same_key else None)

    with ThreadPoolExecutor(max_workers=3) as pool:
        outcomes = list(pool.map(submit, range(3)))
    assert all(outcome.status_code in (200, 201) for outcome in outcomes), [r.text for r in outcomes]
    db.expire_all()
    if same_key:
        assert len({outcome.json()["id"] for outcome in outcomes}) == 1
        assert _counts(db) == (1, 1)
    else:
        assert sorted(outcome.json()["attempt_number"] for outcome in outcomes) == [1, 2, 3]
        assert _counts(db) == (3, 3)


def test_student_snapshot_survives_group_change_and_new_members_cannot_submit(client, db, org_a, published):
    assignment, headers, _ = published
    other_user, other_student = _additional_actor(db, org_a)
    db.execute(delete(GroupMember).where(GroupMember.group_id == org_a.group.id, GroupMember.student_id == org_a.student.id))
    db.add(GroupMember(group_id=org_a.group.id, student_id=other_student.id))
    db.commit()
    assert _upload(client, assignment, headers).status_code == 201
    other_headers = auth_headers(org_a.login(client, other_user.email))
    assert client.get(f"{PREFIX}/student/assignments", headers=other_headers).json() == []
    assert client.get(f"{PREFIX}/student/assignments/{assignment['id']}", headers=other_headers).status_code == 404
    assert _upload(client, assignment, other_headers).status_code == 404
    detail = client.get(f"{PREFIX}/student/assignments/{assignment['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["assignment_student_id"] == str(db.scalar(select(AssignmentStudent.id)))


def test_student_teacher_ownership_and_cross_tenant_objects_are_404(client, db, org_a, org_b, published):
    assignment, headers, teacher_headers = published
    submission = _upload(client, assignment, headers).json()
    another_student_user, _ = _additional_actor(db, org_a)
    another_teacher_user, _ = _additional_actor(db, org_a, teacher=True)
    foreign_student = auth_headers(org_b.student_token(client))
    foreign_teacher = auth_headers(org_b.teacher_token(client))
    unauthorized_student = auth_headers(org_a.login(client, another_student_user.email))
    unauthorized_teacher = auth_headers(org_a.login(client, another_teacher_user.email))
    for denied in (foreign_student, foreign_teacher, unauthorized_student, unauthorized_teacher):
        assert client.get(f"{PREFIX}/submissions/{submission['id']}/original", headers=denied).status_code == 404
    for denied in (foreign_teacher, unauthorized_teacher):
        assert client.get(f"{PREFIX}/assignments/{assignment['id']}/submissions", headers=denied).status_code == 404
    assert _upload(client, assignment, foreign_student).status_code == 404
    assert _upload(client, assignment, teacher_headers).status_code == 403
    db.execute(delete(TeacherGroup).where(TeacherGroup.teacher_id == org_a.teacher.id))
    db.commit()
    assert client.get(f"{PREFIX}/submissions/{submission['id']}/original", headers=teacher_headers).status_code == 404


@pytest.mark.parametrize("state", ["DRAFT", "CLOSED"])
def test_unpublished_or_closed_assignment_rejects_upload(client, db, org_a, private_storage, state):
    assignment, _ = _assignment(client, db, org_a, state=state)
    headers = auth_headers(org_a.student_token(client))
    response = _upload(client, assignment, headers)
    assert response.status_code in (404, 409), response.text
    assert _counts(db) == (0, 0)
    assert _files(private_storage) == []
    listing = client.get(f"{PREFIX}/student/assignments", headers=headers)
    assert listing.status_code == 200
    assert [item["state"] for item in listing.json()] == (["CLOSED"] if state == "CLOSED" else [])


def test_late_published_assignment_still_accepts_and_marks_original(client, db, org_a):
    assignment, _ = _assignment(client, db, org_a, due_at=datetime.now(UTC) - timedelta(hours=2))
    response = _upload(client, assignment, auth_headers(org_a.student_token(client)))
    assert response.status_code == 201, response.text
    assert response.json()["is_late"] is True


ATTACKS = [
    ("docm-extension", lambda: docx_bytes(), "macro.docm"),
    ("vba-payload", lambda: docx_bytes(extra={"word/vbaProject.bin": b"macro"}), "renamed.docx"),
    ("macro-content-type", lambda: docx_bytes(content_types=CONTENT_TYPES.replace(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml",
        "application/vnd.ms-word.document.macroEnabled.main+xml",
    )), "renamed.docx"),
    ("ole-encrypted-office", lambda: b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"encrypted" * 100, "protected.docx"),
    ("encrypted-zip-entry", encrypted_zip_bytes, "protected.docx"),
    ("compression-bomb", lambda: docx_bytes(extra={"word/bomb.xml": "A" * 500_000}), "bomb.docx"),
    ("parent-traversal", lambda: docx_bytes(extra={"../outside.xml": "x"}), "unsafe.docx"),
    ("nested-parent-traversal", lambda: docx_bytes(extra={"word/../outside.xml": "x"}), "unsafe.docx"),
    ("absolute-path", lambda: docx_bytes(extra={"/outside.xml": "x"}), "unsafe.docx"),
    ("windows-path", lambda: docx_bytes(extra={"C:\\outside.xml": "x"}), "unsafe.docx"),
    ("corrupt-zip", lambda: b"PK\x03\x04broken", "broken.docx"),
    ("no-content-types", lambda: docx_bytes(omit="[Content_Types].xml"), "broken.docx"),
    ("no-package-rels", lambda: docx_bytes(omit="_rels/.rels"), "broken.docx"),
    ("no-document", lambda: docx_bytes(omit="word/document.xml"), "broken.docx"),
]


@pytest.mark.parametrize("name,payload,filename", ATTACKS, ids=[case[0] for case in ATTACKS])
def test_malicious_uploads_leave_no_submission_job_or_object(client, db, published, private_storage, name, payload, filename):
    assignment, headers, _ = published
    response = _upload(client, assignment, headers, payload(), filename=filename)
    assert response.status_code in (400, 413, 422), (name, response.text)
    assert _counts(db) == (0, 0)
    assert _files(private_storage) == []
    assert "Traceback" not in response.text
    assert str(private_storage.root) not in response.text
    rejected = [event for event in db.scalars(select(AuditLog)).all() if "REJECT" in event.event_type.value]
    assert len(rejected) == 1
    assert "outside.xml" not in json.dumps(rejected[0].event_metadata)


@pytest.mark.parametrize("limit,value,extra", [
    ("DOCX_MAX_ZIP_ENTRIES", 3, {"word/extra.xml": "extra"}),
    ("DOCX_MAX_ENTRY_BYTES", 100, {}),
    ("DOCX_MAX_UNCOMPRESSED_BYTES", 100, {}),
    ("DOCX_MAX_UPLOAD_BYTES", 100, {}),
])
def test_configured_docx_limits_leave_no_artifacts(client, db, published, private_storage, monkeypatch, limit, value, extra):
    monkeypatch.setattr(settings, limit, value)
    assignment, headers, _ = published
    response = _upload(client, assignment, headers, docx_bytes(extra=extra))
    assert response.status_code in (400, 413, 422), response.text
    assert _counts(db) == (0, 0)
    assert _files(private_storage) == []


@pytest.mark.parametrize("guard_changes", [
    {"upload_user_max_files": 1},
    {"upload_user_max_bytes": 1000},
    {"upload_org_max_storage_bytes": 1000},
])
def test_upload_quotas_preserve_only_accepted_original(client, db, published, private_storage, guard_changes):
    original = docx_bytes()
    guard_changes = {key: len(original) + 1 if "bytes" in key else value for key, value in guard_changes.items()}
    guard = MemoryResourceGuard(replace(ResourceProtectionConfig.from_settings(settings), **guard_changes))
    app.dependency_overrides[get_resource_guard] = lambda: guard
    assignment, headers, _ = published
    first = _upload(client, assignment, headers, original)
    assert first.status_code == 201, first.text
    rejected = _upload(client, assignment, headers, original)
    assert rejected.status_code == 429, rejected.text
    assert int(rejected.headers["retry-after"]) > 0
    assert _counts(db) == (1, 1)
    assert len(_files(private_storage)) == 1


def test_storage_failure_leaves_no_database_artifacts(client, db, published, private_storage, monkeypatch):
    def unavailable(*args, **kwargs):
        raise StorageUnavailableError("secret credential and internal filesystem details")

    monkeypatch.setattr(private_storage, "save_new", unavailable)
    assignment, headers, _ = published
    response = _upload(client, assignment, headers)
    assert response.status_code == 503, response.text
    assert "secret credential" not in response.text
    assert _counts(db) == (0, 0)
    assert _files(private_storage) == []


def test_database_failure_removes_only_current_orphan(client, db, published, private_storage, monkeypatch):
    assignment, headers, _ = published
    first = _upload(client, assignment, headers)
    assert first.status_code == 201, first.text
    retained = _files(private_storage)[0]
    retained_bytes = retained.read_bytes()

    def fail_commit():
        raise IntegrityError("test forced commit failure", {}, RuntimeError("sensitive database error"))

    with monkeypatch.context() as patch:
        patch.setattr(db, "commit", fail_commit)
        try:
            response = _upload(client, assignment, headers)
        except IntegrityError:
            response = None
        if response is not None:
            assert response.status_code >= 400
            assert "sensitive database error" not in response.text
    db.rollback()
    assert _counts(db) == (1, 1)
    assert _files(private_storage) == [retained]
    assert retained.read_bytes() == retained_bytes


@pytest.mark.parametrize("column,value", [
    ("storage_key", "orgs/attacker/replace.docx"),
    ("original_filename", "replacement.docx"),
    ("sha256", "a" * 64),
    ("size_bytes", 1),
    ("attempt_number", 99),
    ("preflight_schema_version", 2),
])
def test_direct_sql_cannot_change_original_metadata(client, db, published, column, value):
    assignment, headers, _ = published
    response = _upload(client, assignment, headers)
    assert response.status_code == 201, response.text
    # Fixed parametrization supplies column names; no caller controls SQL.
    with pytest.raises(DBAPIError):
        db.execute(text(f"UPDATE student_document_submissions SET {column} = :value WHERE id = :id"), {
            "value": value, "id": uuid.UUID(response.json()["id"]),
        })
        db.commit()
    db.rollback()
    assert _counts(db) == (1, 1)


def test_direct_sql_cannot_delete_original_or_job(client, db, published):
    assignment, headers, _ = published
    response = _upload(client, assignment, headers)
    assert response.status_code == 201, response.text
    for table in ("student_document_submissions", "document_check_jobs"):
        with pytest.raises(DBAPIError):
            db.execute(text(f"DELETE FROM {table}"))
            db.commit()
        db.rollback()
    assert _counts(db) == (1, 1)


def test_document_check_feature_flag_hides_student_pipeline(client, published, monkeypatch):
    assignment, headers, _ = published
    monkeypatch.setattr(settings, "DOCUMENT_CHECK_ENABLED", False)
    assert client.get(f"{PREFIX}/student/assignments", headers=headers).status_code == 404
    assert _upload(client, assignment, headers).status_code == 404


def test_database_requires_job_and_exact_roster_tenant(client, db, org_b, published):
    assignment, headers, _ = published
    accepted = _upload(client, assignment, headers)
    assert accepted.status_code == 201, accepted.text
    row = db.scalar(select(StudentDocumentSubmission))
    values = {column.name: getattr(row, column.name) for column in StudentDocumentSubmission.__table__.columns}
    values.update(id=uuid.uuid4(), storage_key="test/new-original.docx", idempotency_key="new-key", attempt_number=2)
    # A valid append without its job is rejected at COMMIT, by a deferred trigger.
    with pytest.raises(DBAPIError):
        db.execute(StudentDocumentSubmission.__table__.insert().values(**values))
        db.commit()
    db.rollback()
    for mismatch in ({"organization_id": org_b.org.id}, {"student_id": org_b.student.id},
                     {"assignment_student_id": uuid.uuid4()}, {"attempt_number": 4}):
        with pytest.raises(DBAPIError):
            db.execute(StudentDocumentSubmission.__table__.insert().values(**{**values, **mismatch}))
            db.commit()
        db.rollback()
    # One job per submission is a database unique constraint, not a service convention.
    job = db.scalar(select(DocumentCheckJob))
    with pytest.raises(IntegrityError):
        db.execute(DocumentCheckJob.__table__.insert().values(
            id=uuid.uuid4(), organization_id=job.organization_id, submission_id=job.submission_id,
            status="QUEUED", queued_at=job.queued_at,
        ))
        db.commit()
    db.rollback()
    assert _counts(db) == (1, 1)


def test_storage_collision_never_deletes_previous_original(client, db, published, private_storage, monkeypatch):
    from app.services import document_submission_service

    assignment, headers, _ = published
    assert _upload(client, assignment, headers).status_code == 201
    row = db.scalar(select(StudentDocumentSubmission))
    key = row.storage_key
    original = private_storage.get(key)
    monkeypatch.setattr(document_submission_service, "build_submission_storage_key", lambda *args: key)
    rejected = _upload(client, assignment, headers, docx_bytes(body="replacement"))
    assert rejected.status_code == 503
    assert private_storage.get(key) == original
    assert _counts(db) == (1, 1)


def test_request_rate_and_envelope_limits_leave_no_artifacts(client, db, published, private_storage, monkeypatch):
    assignment, headers, _ = published
    guard = MemoryResourceGuard(replace(ResourceProtectionConfig.from_settings(settings), upload_rate_requests=1))
    app.dependency_overrides[get_resource_guard] = lambda: guard
    assert _upload(client, assignment, headers, b"not DOCX").status_code == 400
    assert _upload(client, assignment, headers).status_code == 429
    monkeypatch.setattr(settings, "DOCX_MAX_UPLOAD_BYTES", 1)
    envelope = _upload(client, assignment, headers, b"X" * 70_000)
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


def test_analyzer_job_persists_findings_and_exposes_only_authorized_results(
    client, db, org_a, org_b, published, private_storage,
):
    assignment, student_headers, teacher_headers = published
    original = docx_bytes(body="Private content must not enter analyzer results", title_page=True)
    accepted = _upload(client, assignment, student_headers, original)
    assert accepted.status_code == 201, accepted.text
    submission_id = uuid.UUID(accepted.json()["id"])

    service = DocumentCheckJobService(db)
    job = service.claim_next("integration-worker")
    assert job is not None
    assert job.status == DocumentCheckJobStatus.PROCESSING
    assert job.attempt_count == 1
    submission, rules = service.payload(job.id, "integration-worker")
    findings, summary = analyze_document(io.BytesIO(private_storage.get(submission.storage_key)), rules, max_findings=5000)
    assert service.complete(job.id, "integration-worker", findings, summary)

    db.expire_all()
    stored_job = db.get(DocumentCheckJob, job.id)
    assert stored_job.status == DocumentCheckJobStatus.COMPLETED
    assert stored_job.result_summary["rules_evaluated"] == 1
    assert stored_job.result_summary["rules_skipped"] == 0
    assert stored_job.result_summary["findings_count"] == len(findings) > 0
    assert len(db.scalars(select(DocumentCheckFinding)).all()) == len(findings)

    for headers in (student_headers, teacher_headers):
        response = client.get(f"{PREFIX}/submissions/{submission_id}/findings", headers=headers)
        assert response.status_code == 200, response.text
        assert response.headers["x-total-count"] == str(len(findings))
        serialized = json.dumps(response.json())
        assert "Private content" not in serialized
        assert all("storage_key" not in item for item in response.json())
    assert client.get(
        f"{PREFIX}/submissions/{submission_id}/findings",
        headers=auth_headers(org_b.student_token(client)),
    ).status_code == 404
    assert private_storage.get(submission.storage_key) == original

    events = {event.event_type for event in db.scalars(select(AuditLog)).all()}
    assert AuditEventType.DOCUMENT_CHECK_JOB_STARTED in events
    assert AuditEventType.DOCUMENT_CHECK_JOB_COMPLETED in events

    finding_id = db.scalar(select(DocumentCheckFinding.id))
    with pytest.raises(DBAPIError):
        db.execute(text("UPDATE document_check_findings SET code = 'REWRITTEN' WHERE id = :id"), {"id": finding_id})
        db.commit()
    db.rollback()
    with pytest.raises(DBAPIError):
        db.execute(text("UPDATE document_check_jobs SET result_summary = '{}'::jsonb WHERE id = :id"), {"id": job.id})
        db.commit()
    db.rollback()


def test_worker_claims_are_exclusive_and_failures_are_bounded(client, db, published, monkeypatch):
    assignment, headers, _ = published
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
    assignment, headers, _ = published
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
    assert job.result_summary["rules_evaluated"] == 1
    submission = db.scalar(select(StudentDocumentSubmission))
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
    assignment, headers, _ = published
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
    assignment, headers, _ = published
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

    monkeypatch.setattr(settings, "DOCUMENT_CHECK_STUDENT_SUBMISSIONS_ENABLED", False)
    assert client.get(f"{PREFIX}/student/assignments", headers=student_headers).status_code == 404
