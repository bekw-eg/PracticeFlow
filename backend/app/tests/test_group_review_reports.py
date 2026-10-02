"""Group presentation evidence, authorization and persistent artifact tests."""
# ruff: noqa: F811 -- pytest fixtures intentionally shadow imported fixtures
import importlib.util
import io
import uuid
import zipfile
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.services.group_review_report_service import safe_finding
from app.tests.conftest import auth_headers, engine
from app.tests.test_document_check_phase21 import _additional_actor, private_storage, phase21_database_guards  # noqa: F401
from app.tests.test_review_groups import (
    BASE, accepted, complete, finish_analysis,
    review_guards, setup_group,  # noqa: F401
)


@pytest.fixture(scope="module", autouse=True)
def report_guards(review_guards):  # noqa: F811
    path = Path(__file__).parents[2] / "alembic/versions/5d6e7f8091a2_group_review_reports.py"
    spec = importlib.util.spec_from_file_location("group_report_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration.install_report_guards()
    yield
    with engine.begin() as connection:
        connection.execute(text("DROP TRIGGER IF EXISTS trg_protect_group_review_report ON group_review_reports"))
        connection.execute(text("DROP FUNCTION IF EXISTS pf_protect_group_review_report()"))


def create(client, setup_group, **overrides):
    headers, _, group = setup_group
    return client.post(f"{BASE}/groups/{group}/reports", headers=headers,
                       json={"request_id": str(uuid.uuid4()), "locale": "ru", **overrides})


def write(report, **overrides):
    fields = ("title", "introduction", "conclusions", "selected_rule_types", "finding_ids", "remark_submission_ids")
    return {"revision": report["revision"], **{key: report["content"][key] for key in fields}, **overrides}


def reviewed(client, db, setup_group, count=10, truncated=False, remarks="Иванов: индивидуальное замечание"):
    item = accepted(client, setup_group)
    finish_analysis(db, item["job"]["id"], count=count, truncated=truncated)
    assert complete(client, setup_group[0], item, remarks=remarks).status_code == 200
    return item


def test_report_needs_teacher_completion_and_captures_whole_group(client, db, setup_group):
    assert create(client, setup_group).status_code == 409
    first = accepted(client, setup_group)
    finish_analysis(db, first["job"]["id"], count=10, truncated=True)
    assert create(client, setup_group).status_code == 409
    assert complete(client, setup_group[0], first).status_code == 200
    reviewed(client, db, setup_group, count=2)
    reviewed(client, db, setup_group, count=0)
    accepted(client, setup_group)
    report = create(client, setup_group).json()
    assert report["content"]["title"] == "Результаты проверки работ группы БК 2405"
    assert report["content"]["examples"] == report["content"]["remarks"] == []
    assert report["snapshot"]["summary"] == {
        "total_works": 4, "reviewed_works": 3, "pending_works": 1, "included_works": 3, "truncated_works": 1,
        "violations": [{"rule_type": "PAGE_FORMAT_MARGINS", "violations_count": 12, "works_count": 2}],
    }


def test_snapshot_survives_group_changes_reruns_and_repeated_downloads(client, db, setup_group):
    headers, _, group = setup_group
    first = reviewed(client, db, setup_group)
    request_id = str(uuid.uuid4())
    response = create(client, setup_group, request_id=request_id)
    assert response.status_code == 201, response.text
    report = response.json()
    path = f"{BASE}/groups/{group}/reports/{report['id']}"
    assert create(client, setup_group, request_id=request_id).json()["id"] == report["id"]
    assert create(client, setup_group, request_id=request_id, locale="en").status_code == 409
    findings = client.get(path + "/findings?limit=1&offset=2", headers=headers)
    assert findings.headers["X-Total-Count"] == "10"
    example = findings.json()[0]
    assert set(example) == {"id", "rule_type", "location", "actual", "expected"}
    saved = client.put(path, headers=headers, json=write(report, finding_ids=[example["id"]], conclusions="Проверка частичная"))
    assert saved.status_code == 200, saved.text
    current = saved.json()
    assert current["content"]["examples"] == [example]
    assert client.put(path, headers=headers, json=write(report)).status_code == 409
    client.put(f"{BASE}/groups/{group}", headers=headers, json={"name": "Переименованная группа"})
    accepted(client, setup_group)
    doc = f"{BASE}/submissions/{first['id']}"
    settings = client.get(doc + "/settings", headers=headers).json()
    rerun = client.post(doc + "/recheck", headers={**headers, "Idempotency-Key": "report-rerun"}, json={"revision": settings["revision"]})
    assert rerun.status_code == 200
    # A new queued job cannot retarget the report, even before it completes.
    assert client.get(path, headers=headers).json()["snapshot"] == report["snapshot"]
    assert client.get(path + "/findings", headers=headers).headers["X-Total-Count"] == "10"
    assert client.get(path + "/download", headers=headers).status_code == 409
    exported = client.post(path + "/export", headers=headers, json={"revision": current["revision"]})
    assert exported.status_code == 200, exported.text
    assert exported.json()["generated_at"] is not None
    assert client.post(path + "/export", headers=headers, json={"revision": current["revision"]}).json() == exported.json()
    one = client.get(path + "/download", headers=headers)
    two = client.get(path + "/download", headers=headers)
    assert one.content == two.content and one.status_code == 200
    assert one.headers["Cache-Control"] == "private, no-store"
    with zipfile.ZipFile(io.BytesIO(one.content)) as package:
        combined = b" ".join(package.read(name) for name in package.namelist() if name.endswith(".xml"))
        assert "БК 2405".encode() in combined
        for secret in ("Иванов", "original.docx", "Практика", "индивидуальное замечание", "Переименованная группа", first["id"], first["job"]["id"]):
            assert secret.encode() not in combined
        assert any(name.startswith("ppt/charts/") for name in package.namelist())
        assert any(name.endswith(".xlsx") for name in package.namelist())
    assert client.put(path, headers=headers, json=write(current)).status_code == 409
    listed = client.get(f"{BASE}/groups/{group}/reports?limit=1", headers=headers)
    assert listed.headers["X-Total-Count"] == "1" and listed.json()[0]["generated_at"]
    assert "storage_key" not in exported.json()
    with pytest.raises(DBAPIError):
        db.execute(text("UPDATE group_review_reports SET snapshot = '{}' WHERE id = :id"), {"id": uuid.UUID(report["id"])})
        db.commit()
    db.rollback()


def test_report_owner_tenant_roles_findings_and_remarks_are_scoped(client, db, org_a, org_b, setup_group):
    headers, _, group = setup_group
    own = reviewed(client, db, setup_group)
    report = create(client, setup_group).json()
    path = f"{BASE}/groups/{group}/reports/{report['id']}"
    other, _ = _additional_actor(db, org_a, teacher=True)
    for token, status in ((org_a.login(client, other.email), 404), (org_b.teacher_token(client), 404), (org_a.student_token(client), 403)):
        foreign = auth_headers(token)
        for endpoint in (path, path + "/findings", path + "/download", f"{BASE}/groups/{group}/reports"):
            assert client.get(endpoint, headers=foreign).status_code == status
        assert client.put(path, headers=foreign, json=write(report)).status_code == status
        assert client.post(path + "/export", headers=foreign, json={"revision": 1}).status_code == status
        assert client.post(f"{BASE}/groups/{group}/reports", headers=foreign, json={"request_id": str(uuid.uuid4())}).status_code == status
    # Uncompleted analysis from the same group is not eligible.
    pending = accepted(client, setup_group)
    finish_analysis(db, pending["job"]["id"], count=1)
    from app.models.document_check import DocumentCheckFinding
    foreign_finding = db.query(DocumentCheckFinding).filter_by(job_id=uuid.UUID(pending["job"]["id"])).one()
    assert client.put(path, headers=headers, json=write(report, finding_ids=[str(foreign_finding.id)])).status_code == 404
    assert client.put(path, headers=headers, json=write(report, remark_submission_ids=[pending["id"]])).status_code == 404
    assert client.put(path, headers=headers, json=write(report, selected_rule_types=["HEADINGS"])).status_code == 422
    selected = client.put(path, headers=headers, json=write(report, remark_submission_ids=[own["id"]]))
    assert selected.status_code == 200
    assert selected.json()["content"]["remarks"] == ["Иванов: индивидуальное замечание"]


@pytest.mark.parametrize("locale", ["ru", "kk", "en"])
def test_error_free_group_can_export_without_inventing_findings(client, db, setup_group, locale):
    reviewed(client, db, setup_group, count=0, remarks="")
    response = create(client, setup_group, locale=locale)
    assert response.status_code == 201, response.text
    report = response.json()
    path = f"{BASE}/groups/{setup_group[2]}/reports/{report['id']}"
    assert report["snapshot"]["summary"]["violations"] == []
    assert client.get(path + "/findings", headers=setup_group[0]).json() == []
    assert client.post(path + "/export", headers=setup_group[0], json={"revision": 1}).status_code == 200
    assert client.get(path + "/download", headers=setup_group[0]).content.startswith(b"PK")


def test_example_projection_never_copies_arbitrary_identifying_text():
    from types import SimpleNamespace
    from app.models.enums import CheckRuleType
    finding = SimpleNamespace(id=uuid.uuid4(), rule_type=CheckRuleType.FONTS_SIZES,
        location={"paragraph_index": 2, "student_name": "Student", "part": "private-name.docx", "section_index": "Student"},
        actual={"value": "Student Name", "excerpt": "Private excerpt", "font": "Private Font"},
        expected={"allowed": ["Arial", "Student Name"], "value": 14, "student_name": "Name"})
    projected = safe_finding(finding)
    assert projected["actual"] == {"value": None}
    assert projected["expected"] == {"allowed": ["Arial", None], "value": 14}
    assert projected["location"] == {"paragraph_index": 2}
