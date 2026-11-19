from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models.enums import InternshipStatus, ReportStatus
from app.models.internship import Internship
from app.models.notification import Notification
from app.models.report import Report
from app.services.internship_service import InternshipService
from app.tests.conftest import OrgFixture, auth_headers


def _open_report(db, org: OrgFixture, *, deadline_offset: int, status=ReportStatus.DRAFT, start_offset: int = -20) -> Report:
    today = datetime.now(timezone.utc).date()
    internship = Internship(
        organization_id=org.org.id, group_id=org.group.id, template_version_id=org.template_version.id,
        created_by_teacher_id=org.teacher.id, title="Practice",
        start_date=today + timedelta(days=start_offset), end_date=today + timedelta(days=deadline_offset),
        deadline=today + timedelta(days=deadline_offset), status=InternshipStatus.PUBLISHED,
    )
    db.add(internship)
    db.flush()
    report = Report(organization_id=org.org.id, internship_id=internship.id, student_id=org.student.id, status=status)
    db.add(report)
    db.commit()
    return report


def _digests(db, org: OrgFixture) -> list[Notification]:
    return list(db.scalars(select(Notification).where(
        Notification.organization_id == org.org.id,
        Notification.user_id == org.teacher_user.id,
        Notification.type == "STUDENT_RISK_DIGEST",
    )))


def _poll(client, token: str):
    response = client.get("/api/v1/notifications", headers=auth_headers(token))
    assert response.status_code == 200, response.text
    return response.json()


def test_bell_poll_creates_one_digest_per_group_and_day(client, db, org_a: OrgFixture):
    _open_report(db, org_a, deadline_offset=-1)  # overdue -> RED
    token = org_a.teacher_token(client)

    items = _poll(client, token)
    _poll(client, token)  # polling again must not duplicate

    digests = _digests(db, org_a)
    assert len(digests) == 1
    assert digests[0].link == f"/groups/{org_a.group.id}"
    assert digests[0].body == org_a.group.name
    assert any(item["type"] == "STUDENT_RISK_DIGEST" for item in items)


def test_no_digest_without_red_students(client, db, org_a: OrgFixture):
    _open_report(db, org_a, deadline_offset=-1, status=ReportStatus.SUBMITTED)  # handed in
    _open_report(db, org_a, deadline_offset=10)  # far from the deadline
    _poll(client, org_a.teacher_token(client))
    assert _digests(db, org_a) == []


def test_digest_repeats_on_the_next_day_while_still_red(db, org_a: OrgFixture):
    _open_report(db, org_a, deadline_offset=-1)
    service = InternshipService(db)
    now = datetime.now(timezone.utc)
    assert service.create_risk_digest_for_teacher(org_a.org.id, org_a.teacher_user.id, org_a.teacher.id, now=now) == 1
    assert service.create_risk_digest_for_teacher(org_a.org.id, org_a.teacher_user.id, org_a.teacher.id, now=now) == 0
    assert service.create_risk_digest_for_teacher(org_a.org.id, org_a.teacher_user.id, org_a.teacher.id,
                                                  now=now + timedelta(days=1)) == 1
    assert len(_digests(db, org_a)) == 2


def test_other_organizations_students_are_never_counted(client, db, org_a: OrgFixture, org_b: OrgFixture):
    _open_report(db, org_b, deadline_offset=-1)
    _poll(client, org_a.teacher_token(client))
    assert _digests(db, org_a) == []
    assert _digests(db, org_b) == []  # org_b's teacher has not polled


def test_students_do_not_receive_teacher_digests(client, db, org_a: OrgFixture):
    _open_report(db, org_a, deadline_offset=-1)
    items = _poll(client, org_a.student_token(client))
    assert all(item["type"] != "STUDENT_RISK_DIGEST" for item in items)
    assert _digests(db, org_a) == []


def test_naive_time_is_rejected(db, org_a: OrgFixture):
    import pytest

    with pytest.raises(ValueError):
        InternshipService(db).create_risk_digest_for_teacher(org_a.org.id, org_a.teacher_user.id, org_a.teacher.id,
                                                             now=datetime(2026, 6, 1))
