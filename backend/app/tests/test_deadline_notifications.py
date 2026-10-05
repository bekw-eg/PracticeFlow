from datetime import date, datetime, time, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.models.enums import InternshipStatus, ReportStatus
from app.models.internship import Internship
from app.models.notification import Notification
from app.models.report import Report
from app.services.internship_service import InternshipService
from app.tests.conftest import OrgFixture, auth_headers


def _add_open_report(db, org: OrgFixture, *, deadline: date) -> Report:
    internship = Internship(
        organization_id=org.org.id,
        group_id=org.group.id,
        template_version_id=org.template_version.id,
        created_by_teacher_id=org.teacher.id,
        title=f"Practice until {deadline.isoformat()}",
        start_date=deadline - timedelta(days=14),
        end_date=deadline,
        deadline=deadline,
        status=InternshipStatus.PUBLISHED,
    )
    db.add(internship)
    db.flush()
    report = Report(
        organization_id=org.org.id,
        internship_id=internship.id,
        student_id=org.student.id,
        status=ReportStatus.DRAFT,
    )
    db.add(report)
    db.commit()
    return report


@pytest.mark.parametrize(
    ("days_from_deadline", "expected_type"),
    [
        (-4, None),
        (-3, "REPORT_DEADLINE_SOON"),
        (-1, "REPORT_DEADLINE_SOON"),
        (0, "REPORT_DEADLINE_TODAY"),
        (1, "REPORT_DEADLINE_OVERDUE"),
    ],
)
def test_deadline_reminder_uses_the_current_date_window(db, org_a: OrgFixture, days_from_deadline: int, expected_type: str | None):
    deadline = date(2026, 6, 12)
    report = _add_open_report(db, org_a, deadline=deadline)

    created = InternshipService(db).create_deadline_reminders_for_student(
        org_a.org.id,
        org_a.student_user.id,
        now=datetime.combine(deadline + timedelta(days=days_from_deadline), time(12), tzinfo=timezone.utc),
    )

    notifications = list(db.scalars(select(Notification).where(Notification.organization_id == org_a.org.id)))
    assert created == (1 if expected_type else 0)
    assert [item.type for item in notifications] == ([] if expected_type is None else [expected_type])
    if expected_type:
        assert notifications[0].link == f"/reports/{report.id}/edit"


def test_deadline_reminder_uses_utc_date_at_a_timezone_boundary(db, org_a: OrgFixture):
    report = _add_open_report(db, org_a, deadline=date(2026, 6, 12))
    # It is already June 13 at UTC+14, but still June 12 in UTC. Deadline
    # dates are API-wide UTC dates, so this is the due-today reminder.
    now = datetime(2026, 6, 13, 0, 30, tzinfo=timezone(timedelta(hours=14)))

    created = InternshipService(db).create_deadline_reminders_for_student(org_a.org.id, org_a.student_user.id, now=now)

    item = db.scalar(select(Notification).where(Notification.organization_id == org_a.org.id))
    assert created == 1
    assert item is not None
    assert item.type == "REPORT_DEADLINE_TODAY"
    assert item.link == f"/reports/{report.id}/edit"


def test_deadline_reminders_are_idempotent_for_repeated_polling(db, org_a: OrgFixture):
    deadline = date(2026, 6, 12)
    _add_open_report(db, org_a, deadline=deadline)
    service = InternshipService(db)
    now = datetime(2026, 6, 12, 9, tzinfo=timezone.utc)

    assert service.create_deadline_reminders_for_student(org_a.org.id, org_a.student_user.id, now=now) == 1
    assert service.create_deadline_reminders_for_student(org_a.org.id, org_a.student_user.id, now=now) == 0

    assert db.scalar(
        select(func.count()).select_from(Notification).where(Notification.organization_id == org_a.org.id)
    ) == 1


def test_deadline_reminders_do_not_cross_tenant_scope(db, org_a: OrgFixture, org_b: OrgFixture):
    deadline = date(2026, 6, 12)
    report_a = _add_open_report(db, org_a, deadline=deadline)
    _add_open_report(db, org_b, deadline=deadline)

    created = InternshipService(db).create_deadline_reminders_for_student(
        org_a.org.id,
        org_a.student_user.id,
        now=datetime(2026, 6, 12, 9, tzinfo=timezone.utc),
    )

    own = list(db.scalars(select(Notification).where(Notification.organization_id == org_a.org.id)))
    other_tenant = list(db.scalars(select(Notification).where(Notification.organization_id == org_b.org.id)))
    assert created == 1
    assert len(own) == 1
    assert own[0].user_id == org_a.student_user.id
    assert own[0].link == f"/reports/{report_a.id}/edit"
    assert other_tenant == []


def test_notification_endpoint_materializes_the_current_students_reminder(client, db, org_a: OrgFixture):
    report = _add_open_report(db, org_a, deadline=datetime.now(timezone.utc).date())
    token = org_a.student_token(client)

    response = client.get("/api/v1/notifications", headers=auth_headers(token))

    assert response.status_code == 200
    assert response.json()[0]["type"] == "REPORT_DEADLINE_TODAY"
    assert response.json()[0]["link"] == f"/reports/{report.id}/edit"
