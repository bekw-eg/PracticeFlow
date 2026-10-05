from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api.v1.reports import _deadline_state
from app.schemas.internship import CreateInternshipRequest
from app.schemas.report import ReportDeadlineState
from app.tests.conftest import OrgFixture, auth_headers


def test_group_detail_lists_students(client, db, org_a: OrgFixture):
    from app.models.group_member import GroupMember

    db.add(GroupMember(group_id=org_a.group.id, student_id=org_a.student.id))
    db.commit()

    token = org_a.teacher_token(client)
    resp = client.get(f"/api/v1/groups/{org_a.group.id}", headers=auth_headers(token))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["students"]) == 1
    assert body["students"][0]["email"] == org_a.student_user.email


def _internship_payload(template_version_id, title="Practice Internship"):
    return {
        "title": title,
        "template_version_id": str(template_version_id),
        "start_date": "2025-06-01",
        "end_date": "2025-07-15",
        "deadline": "2025-07-20",
    }


def test_internship_description_is_limited_to_two_thousand_characters():
    payload = {
        "title": "Practice Internship",
        "template_version_id": uuid4(),
        "start_date": "2026-06-01",
        "end_date": "2026-07-15",
        "deadline": "2026-07-20",
    }
    assert CreateInternshipRequest(**payload, description="Student instructions").description == "Student instructions"
    with pytest.raises(ValidationError):
        CreateInternshipRequest(**payload, description="x" * 2001)


def test_deadline_state_distinguishes_upcoming_due_and_submitted_reports():
    today = date(2026, 9, 1)

    assert _deadline_state(today + timedelta(days=4), None, today=today) == ReportDeadlineState.UPCOMING
    assert _deadline_state(today + timedelta(days=3), None, today=today) == ReportDeadlineState.DUE_SOON
    assert _deadline_state(today, None, today=today) == ReportDeadlineState.DUE_TODAY
    assert _deadline_state(today - timedelta(days=1), None, today=today) == ReportDeadlineState.OVERDUE
    assert _deadline_state(today, datetime(2026, 9, 1, 12, tzinfo=timezone.utc), today=today) == ReportDeadlineState.SUBMITTED_ON_TIME
    assert _deadline_state(today, datetime(2026, 9, 2, 12, tzinfo=timezone.utc), today=today) == ReportDeadlineState.SUBMITTED_LATE


def test_student_report_list_exposes_internship_context_without_document_content(client, db, org_a: OrgFixture):
    from app.models.group_member import GroupMember

    today = datetime.now(timezone.utc).date()
    db.add(GroupMember(group_id=org_a.group.id, student_id=org_a.student.id))
    db.commit()

    teacher_token = org_a.teacher_token(client)
    create_response = client.post(
        f"/api/v1/groups/{org_a.group.id}/internships",
        headers=auth_headers(teacher_token),
        json={
            "title": "Frontend practice",
            "description": "Prepare the practice diary before submitting the report.",
            "template_version_id": str(org_a.template_version.id),
            "start_date": (today - timedelta(days=7)).isoformat(),
            "end_date": (today + timedelta(days=7)).isoformat(),
            "deadline": (today + timedelta(days=2)).isoformat(),
        },
    )
    internship_id = create_response.json()["id"]
    assert client.post(f"/api/v1/internships/{internship_id}/publish", headers=auth_headers(teacher_token)).status_code == 200

    student_response = client.get("/api/v1/reports", headers=auth_headers(org_a.student_token(client)))

    assert student_response.status_code == 200
    report = student_response.json()[0]
    assert report["internship_title"] == "Frontend practice"
    assert report["internship_description"] == "Prepare the practice diary before submitting the report."
    assert report["group_name"] == org_a.group.name
    assert report["start_date"] == (today - timedelta(days=7)).isoformat()
    assert report["end_date"] == (today + timedelta(days=7)).isoformat()
    assert report["deadline"] == (today + timedelta(days=2)).isoformat()
    assert report["deadline_state"] == "DUE_SOON"
    assert "document" not in report
    assert "document_data" not in report


def test_create_internship_fixes_template_version_permanently(client, db, org_a: OrgFixture):
    """Rule 9: once created, an internship's template_version_id must never
    change even if a newer version of the same template is later created."""
    token = org_a.teacher_token(client)

    create_resp = client.post(
        f"/api/v1/groups/{org_a.group.id}/internships",
        headers=auth_headers(token),
        json=_internship_payload(org_a.template_version.id),
    )
    assert create_resp.status_code == 201
    internship_id = create_resp.json()["id"]
    assert create_resp.json()["template_version_id"] == str(org_a.template_version.id)

    # Teacher creates a new version of the same template afterwards...
    v2_resp = client.post(
        f"/api/v1/templates/{org_a.template.id}/versions",
        headers=auth_headers(token),
        json={"meta": {"default_font_size": 12}},
    )
    assert v2_resp.status_code == 201
    assert v2_resp.json()["version_number"] == 2

    # ...and the existing internship must still point at v1.
    internships_resp = client.get(f"/api/v1/groups/{org_a.group.id}/internships", headers=auth_headers(token))
    fetched = next(i for i in internships_resp.json() if i["id"] == internship_id)
    assert fetched["template_version_id"] == str(org_a.template_version.id)


def test_template_reused_across_second_group(client, db, org_a: OrgFixture):
    """The core product concept: My Groups -> BK2405 creates a template ->
    BK2404 reuses the same template_version_id."""
    from app.models.group import Group
    from app.models.teacher_group import TeacherGroup

    second_group = Group(organization_id=org_a.org.id, name="BK-SECOND")
    db.add(second_group)
    db.flush()
    db.add(TeacherGroup(teacher_id=org_a.teacher.id, group_id=second_group.id))
    db.commit()

    token = org_a.teacher_token(client)

    first = client.post(
        f"/api/v1/groups/{org_a.group.id}/internships",
        headers=auth_headers(token),
        json=_internship_payload(org_a.template_version.id, title="First group internship"),
    )
    assert first.status_code == 201

    second = client.post(
        f"/api/v1/groups/{second_group.id}/internships",
        headers=auth_headers(token),
        json=_internship_payload(org_a.template_version.id, title="Second group internship, reused template"),
    )
    assert second.status_code == 201
    assert second.json()["template_version_id"] == str(org_a.template_version.id)


def test_publish_creates_report_for_every_current_group_member(client, db, org_a: OrgFixture):
    from app.core.security import hash_password
    from app.models.group_member import GroupMember
    from app.models.membership import OrganizationMembership
    from app.models.student import Student
    from app.models.user import User

    db.add(GroupMember(group_id=org_a.group.id, student_id=org_a.student.id))
    second_user = User(email="second-student@org-a.edu", hashed_password=hash_password("Practice123!"), full_name="Second Student")
    db.add(second_user)
    db.flush()
    second_membership = OrganizationMembership(user_id=second_user.id, organization_id=org_a.org.id, role_id=org_a.role_student.id)
    db.add(second_membership)
    db.flush()
    second_student = Student(membership_id=second_membership.id)
    db.add(second_student)
    db.flush()
    db.add(GroupMember(group_id=org_a.group.id, student_id=second_student.id))
    db.commit()

    token = org_a.teacher_token(client)
    create_resp = client.post(
        f"/api/v1/groups/{org_a.group.id}/internships", headers=auth_headers(token), json=_internship_payload(org_a.template_version.id)
    )
    internship_id = create_resp.json()["id"]

    publish_resp = client.post(f"/api/v1/internships/{internship_id}/publish", headers=auth_headers(token))
    assert publish_resp.status_code == 200
    assert publish_resp.json()["status"] == "PUBLISHED"

    reports_resp = client.get(f"/api/v1/groups/{org_a.group.id}/reports", headers=auth_headers(token))
    assert reports_resp.status_code == 200
    assert len(reports_resp.json()) == 2
    assert all(r["status"] == "DRAFT" for r in reports_resp.json())


def test_submit_creates_immutable_version_and_preserves_history_on_resubmit(client, db, org_a: OrgFixture):
    from app.models.group_member import GroupMember

    db.add(GroupMember(group_id=org_a.group.id, student_id=org_a.student.id))
    db.commit()

    teacher_token = org_a.teacher_token(client)
    create_resp = client.post(
        f"/api/v1/groups/{org_a.group.id}/internships", headers=auth_headers(teacher_token), json=_internship_payload(org_a.template_version.id)
    )
    internship_id = create_resp.json()["id"]
    client.post(f"/api/v1/internships/{internship_id}/publish", headers=auth_headers(teacher_token))

    student_token = org_a.student_token(client)
    reports = client.get("/api/v1/reports", headers=auth_headers(student_token)).json()
    report_id = reports[0]["id"]

    submit1 = client.post(f"/api/v1/reports/{report_id}/submit", headers=auth_headers(student_token))
    assert submit1.status_code == 200
    assert submit1.json()["status"] == "SUBMITTED"
    v1_id = submit1.json()["current_version_id"]

    detail = client.get(f"/api/v1/reports/{report_id}", headers=auth_headers(student_token)).json()
    assert len(detail["versions"]) == 1
    assert detail["versions"][0]["version_number"] == 1

    # Simulate a teacher review outcome directly at the DB layer (the review
    # endpoint itself is Phase 3), then confirm resubmission creates v2
    # without touching v1 — proving the immutable-versioning mechanics.
    from app.models.enums import ReportStatus
    from app.models.report import Report
    from sqlalchemy import select

    report_row = db.execute(select(Report).where(Report.id == report_id)).scalar_one()
    report_row.status = ReportStatus.REVISION_REQUIRED
    db.commit()

    submit2 = client.post(f"/api/v1/reports/{report_id}/submit", headers=auth_headers(student_token))
    assert submit2.status_code == 200
    v2_id = submit2.json()["current_version_id"]
    assert v2_id != v1_id

    detail2 = client.get(f"/api/v1/reports/{report_id}", headers=auth_headers(student_token)).json()
    version_numbers = sorted(v["version_number"] for v in detail2["versions"])
    assert version_numbers == [1, 2]


def test_student_cannot_submit_another_students_report(client, db, org_a: OrgFixture):
    from app.core.security import hash_password
    from app.models.group_member import GroupMember
    from app.models.membership import OrganizationMembership
    from app.models.student import Student
    from app.models.user import User

    db.add(GroupMember(group_id=org_a.group.id, student_id=org_a.student.id))
    db.commit()

    teacher_token = org_a.teacher_token(client)
    create_resp = client.post(
        f"/api/v1/groups/{org_a.group.id}/internships", headers=auth_headers(teacher_token), json=_internship_payload(org_a.template_version.id)
    )
    internship_id = create_resp.json()["id"]
    client.post(f"/api/v1/internships/{internship_id}/publish", headers=auth_headers(teacher_token))

    student_token = org_a.student_token(client)
    reports = client.get("/api/v1/reports", headers=auth_headers(student_token)).json()
    report_id = reports[0]["id"]

    intruder_user = User(email="intruder@org-a.edu", hashed_password=hash_password("Practice123!"), full_name="Intruder")
    db.add(intruder_user)
    db.flush()
    intruder_membership = OrganizationMembership(user_id=intruder_user.id, organization_id=org_a.org.id, role_id=org_a.role_student.id)
    db.add(intruder_membership)
    db.flush()
    db.add(Student(membership_id=intruder_membership.id))
    db.commit()

    intruder_token = org_a.login(client, intruder_user.email)
    resp = client.post(f"/api/v1/reports/{report_id}/submit", headers=auth_headers(intruder_token))
    assert resp.status_code == 403
