"""API, PostgreSQL constraints and pinned-run aggregation regressions."""
import importlib.util
import uuid
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.config import settings
from app.models.enums import DocumentCheckJobStatus
from app.services.document_analyzer import ANALYZER_VERSION, AnalyzerFinding
from app.services.document_check_job_service import DocumentCheckJobService
from app.tests.conftest import auth_headers, engine
from app.tests.test_document_check_phase1 import _create_published_profile
from app.tests.test_document_check_phase21 import (
    MIME, _additional_actor, docx_bytes,
    phase21_database_guards, private_storage,  # noqa: F401 -- shared fixtures, including production triggers
)

BASE = "/api/v1/document-checks/teacher"
DOCX = docx_bytes(title_page=True)


@pytest.fixture(scope="module", autouse=True)
def review_guards(phase21_database_guards):  # noqa: F811
    path = Path(__file__).parents[2] / "alembic/versions/4c5d6e7f8091_review_groups.py"
    spec = importlib.util.spec_from_file_location("review_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration.install_review_guards()
    yield
    with engine.begin() as connection:
        connection.execute(text("DROP FUNCTION pf_protect_teacher_review() CASCADE"))


@pytest.fixture
def setup_group(client, org_a):
    _, version = _create_published_profile(client, org_a)
    headers = auth_headers(org_a.teacher_token(client))
    response = client.post(f"{BASE}/groups", headers=headers, json={"name": " БК 2405 ", "description": "Отчёты"})
    assert response.status_code == 201, response.text
    return headers, version["id"], response.json()["id"]


def upload(client, setup_group, *, key=None, **overrides):
    headers, version, group = setup_group
    data = {"profile_version_id": version, "review_group_id": group, "student_label": "Иванов",
            "work_title": "Практика", "work_type": "REPORT", **overrides}
    return client.post(f"{BASE}/submissions", headers={**headers, "Idempotency-Key": key or str(uuid.uuid4())},
                       data={k: v for k, v in data.items() if v is not None},
                       files={"file": ("original.docx", DOCX, MIME)})


def accepted(client, setup_group, **overrides):
    response = upload(client, setup_group, **overrides)
    assert response.status_code == 201, response.text
    return response.json()


def finish_analysis(db, expected_id, count=10, truncated=False):
    service = DocumentCheckJobService(db)
    job = service.claim_next("review-test")
    assert str(job.id) == expected_id
    _, rules = service.payload(job.id, "review-test")
    rule = rules[0]
    findings = [AnalyzerFinding(rule.id, rule.rule_type, rule.category, rule.severity,
                                "PAGE_MARGIN_MISMATCH", "margin_top_mm", {"section_index": i + 1},
                                {"value": 20}, {"value": 10}) for i in range(count)]
    assert service.complete(job.id, "review-test", findings, {
        "analyzer_version": ANALYZER_VERSION, "rules_total": len(rules), "rules_evaluated": len(rules),
        "rules_skipped": 0, "findings_count": count, "findings_truncated": truncated,
    })


def complete(client, headers, item, **values):
    return client.post(f"{BASE}/submissions/{item['id']}/review/complete", headers=headers,
                       json={"revision": 0, "remarks": "Проверено", "job_id": item["job"]["id"], **values})


def test_group_create_edit_list_and_access(client, db, org_a, org_b, setup_group):
    headers, _, group_id = setup_group
    path = f"{BASE}/groups/{group_id}"
    assert client.get(path, headers=headers).json()["name"] == "БК 2405"
    changed = client.put(path, headers=headers, json={"name": "БК 2406", "description": None})
    assert changed.status_code == 200 and changed.json()["description"] is None
    client.post(f"{BASE}/groups", headers=headers, json={"name": "БК 2407"})
    page = client.get(f"{BASE}/groups?limit=1&offset=1", headers=headers)
    assert len(page.json()) == 1 and page.headers["X-Total-Count"] == "2"
    assert client.post(f"{BASE}/groups", headers=headers, json={"name": "  "}).status_code == 422
    other, _ = _additional_actor(db, org_a, teacher=True)
    for token, expected in ((org_a.login(client, other.email), 404), (org_b.teacher_token(client), 404),
                             (org_a.student_token(client), 403)):
        foreign = auth_headers(token)
        for suffix in ("", "/works", "/summary"):
            assert client.get(path + suffix, headers=foreign).status_code == expected
        assert client.put(path, headers=foreign, json={"name": "leak"}).status_code == expected
        own_list = client.get(f"{BASE}/groups", headers=foreign)
        assert own_list.status_code == (403 if expected == 403 else 200)
        if expected == 404:
            assert own_list.json() == []


def test_upload_group_identity_metadata_security_and_legacy(client, db, org_a, org_b, setup_group):
    headers, version, group = setup_group
    item = accepted(client, setup_group, key="same")
    assert item["review_group_id"] == group and item["work_type"] == "REPORT"
    assert item["teacher_review"] is None
    assert client.get(f"{BASE}/submissions/{item['id']}", headers=headers).headers["Cache-Control"] == "private, no-store"
    original = client.get(f"{BASE}/submissions/{item['id']}/original", headers=headers)
    assert original.content == DOCX
    assert upload(client, setup_group, key="same").status_code == 200
    second_group = client.post(f"{BASE}/groups", headers=headers, json={"name": "Other"}).json()["id"]
    for override in ({"review_group_id": second_group}, {"work_type": "COURSEWORK"}, {"work_title": "Other"}):
        assert upload(client, setup_group, key="same", **override).status_code == 409
    for override in ({"work_title": " "}, {"student_label": None}, {"work_type": "OTHER"}, {"work_type": None}):
        assert upload(client, setup_group, **override).status_code == 422
    foreign_headers = auth_headers(org_b.teacher_token(client))
    foreign_group = client.post(f"{BASE}/groups", headers=foreign_headers, json={"name": "Private"}).json()["id"]
    assert upload(client, setup_group, review_group_id=foreign_group).status_code == 404
    other, _ = _additional_actor(db, org_a, teacher=True)
    other_headers = auth_headers(org_a.login(client, other.email))
    assert upload(client, (other_headers, version, group)).status_code == 404
    legacy = accepted(client, setup_group, review_group_id=None, work_title=None, work_type=None, student_label=None)
    assert legacy["review_group_id"] is None
    assert len(client.get(f"{BASE}/groups/{group}/works", headers=headers).json()) == 1


def test_review_remarks_completion_and_conflicts(client, db, org_a, org_b, setup_group):
    headers, _, group = setup_group
    item = accepted(client, setup_group)
    path = f"{BASE}/submissions/{item['id']}"
    assert complete(client, headers, item).status_code == 409
    saved = client.put(path + "/review", headers=headers, json={"revision": 0, "remarks": "Поля исправить"})
    assert saved.status_code == 200, saved.text
    assert saved.json()["completed_at"] is None
    assert client.get(path, headers=headers).json()["teacher_review"]["remarks"] == "Поля исправить"
    assert client.put(path + "/review", headers=headers, json={"revision": 0, "remarks": "Поля исправить"}).json() == saved.json()
    assert client.put(path + "/review", headers=headers, json={"revision": 0, "remarks": "Lost edit"}).status_code == 409
    other, _ = _additional_actor(db, org_a, teacher=True)
    for token, expected in ((org_a.login(client, other.email), 404), (org_b.teacher_token(client), 404), (org_a.student_token(client), 403)):
        foreign = auth_headers(token)
        for suffix in ("", "/original", "/findings", "/runs", f"/runs/{item['job']['id']}"):
            assert client.get(path + suffix, headers=foreign).status_code == expected
        assert client.put(path + "/review", headers=foreign, json={"revision": 1, "remarks": "hack"}).status_code == expected
        assert complete(client, foreign, item, revision=1).status_code == expected
    finish_analysis(db, item["job"]["id"])
    assert client.get(f"{BASE}/groups/{group}/summary", headers=headers).json()["included_works"] == 0
    result = complete(client, headers, item, revision=1, remarks="Final notes")
    assert result.status_code == 200, result.text
    assert result.json()["completed_job_id"] == item["job"]["id"]
    assert result.json()["completed_by_teacher_id"] == str(org_a.teacher.id)
    assert result.json()["completed_at"]
    assert complete(client, headers, item, revision=1, remarks="Final notes").json() == result.json()
    assert client.put(path + "/review", headers=headers, json={"revision": 2, "remarks": "replace"}).status_code == 409


def test_exact_job_and_failed_analysis_cannot_be_confirmed(client, db, setup_group, monkeypatch):
    headers, _, group = setup_group
    item = accepted(client, setup_group)
    other = accepted(client, setup_group)
    assert complete(client, headers, item, job_id=other["job"]["id"]).status_code == 404
    service = DocumentCheckJobService(db)
    running = service.claim_next("failure")
    assert complete(client, headers, item).status_code == 409
    monkeypatch.setattr(settings, "DOCUMENT_CHECK_WORKER_MAX_ATTEMPTS", 1)
    assert service.retry_or_fail(running.id, "failure", "CHECK_ANALYSIS_FAILED") == DocumentCheckJobStatus.FAILED
    assert complete(client, headers, item).status_code == 409
    assert complete(client, headers, item, job_id=str(uuid.uuid4())).status_code == 404
    summary = client.get(f"{BASE}/groups/{group}/summary", headers=headers).json()
    assert summary["pending_works"] == 2 and summary["included_works"] == 0 and summary["violations"] == []


def test_review_group_rollout_flag_hides_new_endpoints(client, setup_group, monkeypatch):
    headers, _, group = setup_group
    item = accepted(client, setup_group)
    monkeypatch.setattr(settings, "DOCUMENT_CHECK_ENABLED", False)
    for suffix in ("", f"/{group}", f"/{group}/works", f"/{group}/summary"):
        assert client.get(f"{BASE}/groups{suffix}", headers=headers).status_code == 404
    assert complete(client, headers, item).status_code == 404


def test_summary_counts_distinct_works_full_group_and_pinned_rechecks(client, db, setup_group):
    headers, _, group = setup_group
    first = accepted(client, setup_group)
    finish_analysis(db, first["job"]["id"], count=10, truncated=True)
    assert complete(client, headers, first).status_code == 200
    second = accepted(client, setup_group)
    finish_analysis(db, second["job"]["id"], count=2)
    assert complete(client, headers, second).status_code == 200
    clean = accepted(client, setup_group)
    finish_analysis(db, clean["job"]["id"], count=0)
    assert complete(client, headers, clean).status_code == 200
    unreviewed = accepted(client, setup_group)
    finish_analysis(db, unreviewed["job"]["id"], count=7)
    path = f"{BASE}/groups/{group}"
    expected = {"total_works": 4, "pending_works": 1, "reviewed_works": 3, "included_works": 3, "truncated_works": 1,
                "violations": [{"rule_type": "PAGE_FORMAT_MARGINS", "violations_count": 12, "works_count": 2}]}
    assert client.get(path + "/summary", headers=headers).json() == expected
    completed_page = client.get(path + "/works?review_status=completed&limit=1&offset=1", headers=headers)
    assert len(completed_page.json()) == 1 and completed_page.headers["X-Total-Count"] == "3"
    assert client.get(path + "/works?review_status=pending", headers=headers).json()[0]["id"] == unreviewed["id"]
    document_path = f"{BASE}/submissions/{first['id']}"
    draft = client.get(document_path + "/settings", headers=headers).json()
    rerun = client.post(document_path + "/recheck", headers={**headers, "Idempotency-Key": "technical"}, json={"revision": draft["revision"]})
    assert rerun.status_code == 200, rerun.text
    assert client.get(path + "/summary", headers=headers).json() == expected
    finish_analysis(db, rerun.json()["id"], count=0)
    db.expire_all()
    assert client.get(path + "/summary", headers=headers).json() == expected
    loaded = client.get(document_path, headers=headers).json()
    assert loaded["job"]["id"] == rerun.json()["id"]
    assert loaded["teacher_review"]["completed_job_id"] == first["job"]["id"]
    assert complete(client, headers, loaded, revision=1).status_code == 409


def test_database_guards_prevent_retargeting_and_overwriting_review(client, db, org_a, org_b, setup_group):
    headers, _, _ = setup_group
    item = accepted(client, setup_group)
    finish_analysis(db, item["job"]["id"])
    assert complete(client, headers, item).status_code == 200
    for sql in ("UPDATE teacher_document_reviews SET remarks = 'changed' WHERE submission_id = :id",
                "DELETE FROM teacher_document_reviews WHERE submission_id = :id",
                "UPDATE teacher_document_submissions SET work_title = 'changed' WHERE id = :id"):
        with pytest.raises(DBAPIError):
            db.execute(text(sql), {"id": uuid.UUID(item["id"])})
            db.commit()
        db.rollback()
    pending = accepted(client, setup_group)
    with pytest.raises(DBAPIError):
        db.execute(text("""INSERT INTO teacher_document_reviews
            (organization_id, submission_id, revision, remarks, completed_at, completed_by_teacher_id, completed_job_id)
            VALUES (:org, :sub, 1, '', now(), :teacher, :job)"""),
            {"org": org_a.org.id, "sub": uuid.UUID(pending["id"]), "teacher": org_a.teacher.id, "job": uuid.UUID(pending["job"]["id"])})
        db.commit()
    db.rollback()
