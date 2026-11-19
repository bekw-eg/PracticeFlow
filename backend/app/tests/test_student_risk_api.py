from datetime import datetime, timedelta, timezone

from app.documents.defaults import build_default_document
from app.models.enums import InternshipStatus, ReportStatus
from app.models.internship import Internship
from app.models.report import Report
from app.tests.conftest import OrgFixture, auth_headers


def _internship(db, org: OrgFixture, *, start_offset: int, deadline_offset: int, status=InternshipStatus.PUBLISHED, title="Practice") -> Internship:
    today = datetime.now(timezone.utc).date()
    internship = Internship(
        organization_id=org.org.id,
        group_id=org.group.id,
        template_version_id=org.template_version.id,
        created_by_teacher_id=org.teacher.id,
        title=title,
        start_date=today + timedelta(days=start_offset),
        end_date=today + timedelta(days=deadline_offset),
        deadline=today + timedelta(days=deadline_offset),
        status=status,
    )
    db.add(internship)
    db.flush()
    return internship


def _report(db, org: OrgFixture, internship: Internship, report_status: ReportStatus, document=None) -> Report:
    report = Report(
        organization_id=org.org.id,
        internship_id=internship.id,
        student_id=org.student.id,
        status=report_status,
        document_data=document,
    )
    db.add(report)
    db.commit()
    return report


def _risk(client, org: OrgFixture, group_id=None):
    token = org.teacher_token(client)
    return client.get(f"/api/v1/groups/{group_id or org.group.id}/student-risk", headers=auth_headers(token))


def test_overdue_draft_is_red_with_reason_and_counts(client, db, org_a: OrgFixture):
    internship = _internship(db, org_a, start_offset=-20, deadline_offset=-2)
    report = _report(db, org_a, internship, ReportStatus.DRAFT)

    response = _risk(client, org_a)

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["red"], body["yellow"], body["green"]) == (1, 0, 0)
    item = body["items"][0]
    assert item["level"] == "RED"
    assert item["reasons"] == ["OVERDUE"]
    assert item["report_id"] == str(report.id)
    assert item["student_name"] == org_a.student_user.full_name
    assert item["report_status"] == "DRAFT"
    assert item["deadline"] == internship.deadline.isoformat()
    assert "document_data" not in item  # no report content is exposed


def test_submitted_report_is_green_and_open_items_sort_first(client, db, org_a: OrgFixture):
    late = _internship(db, org_a, start_offset=-20, deadline_offset=-1, title="Late")
    _report(db, org_a, late, ReportStatus.DRAFT)
    done = _internship(db, org_a, start_offset=-20, deadline_offset=-5, title="Done")
    _report(db, org_a, done, ReportStatus.SUBMITTED)

    body = _risk(client, org_a).json()

    assert [item["level"] for item in body["items"]] == ["RED", "GREEN"]
    assert [item["internship_title"] for item in body["items"]] == ["Late", "Done"]
    assert (body["red"], body["yellow"], body["green"]) == (1, 0, 1)


def test_completion_percent_is_derived_from_written_sections(client, db, org_a: OrgFixture):
    document = build_default_document().model_dump(mode="json")
    editable = [section for section in document["sections"] if section.get("editable", True)]
    assert editable, "default template must contain student-editable sections"
    editable[0]["blocks"] = [{"type": "paragraph", "id": "p1", "style_name": "Normal",
                              "runs": [{"kind": "text", "id": "r1", "text": " ".join(["текст"] * 40)}]}]
    internship = _internship(db, org_a, start_offset=-5, deadline_offset=30)
    _report(db, org_a, internship, ReportStatus.DRAFT, document)

    item = _risk(client, org_a).json()["items"][0]

    assert item["completion_percent"] == round(100 / len(editable))
    assert item["level"] == "GREEN"


def test_draft_and_closed_internships_are_not_listed(client, db, org_a: OrgFixture):
    for status in (InternshipStatus.DRAFT, InternshipStatus.CLOSED):
        internship = _internship(db, org_a, start_offset=-20, deadline_offset=-2, status=status, title=status.value)
        db.add(Report(organization_id=org_a.org.id, internship_id=internship.id, student_id=org_a.student.id,
                      status=ReportStatus.DRAFT))
        db.flush()
    db.commit()

    body = _risk(client, org_a).json()

    assert body == {"red": 0, "yellow": 0, "green": 0, "items": []}


def test_student_cannot_read_risk(client, org_a: OrgFixture):
    token = org_a.student_token(client)
    response = client.get(f"/api/v1/groups/{org_a.group.id}/student-risk", headers=auth_headers(token))
    assert response.status_code == 403


def test_teacher_cannot_read_another_organizations_group(client, db, org_a: OrgFixture, org_b: OrgFixture):
    internship = _internship(db, org_b, start_offset=-20, deadline_offset=-2)
    _report(db, org_b, internship, ReportStatus.DRAFT)

    response = _risk(client, org_a, group_id=org_b.group.id)

    assert response.status_code == 403
    assert "student_name" not in response.text


def test_unauthenticated_request_is_rejected(client, org_a: OrgFixture):
    assert client.get(f"/api/v1/groups/{org_a.group.id}/student-risk").status_code in (401, 403)


def test_deadline_day_with_nothing_written_is_red(client, db, org_a: OrgFixture):
    internship = _internship(db, org_a, start_offset=-10, deadline_offset=0)
    _report(db, org_a, internship, ReportStatus.DRAFT)

    item = _risk(client, org_a).json()["items"][0]

    assert item["level"] == "RED"  # deadline day, nothing written
    assert item["reasons"] == ["DEADLINE_SOON_LOW_PROGRESS"]
