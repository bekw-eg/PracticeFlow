from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models.comment import Comment
from app.models.enums import CommentStatus, InternshipStatus, ReportStatus
from app.models.group import Group
from app.models.internship import Internship
from app.models.report import Report
from app.models.report_version import ReportVersion
from app.tests.conftest import OrgFixture, auth_headers


def _add_queue_report(
    db,
    org: OrgFixture,
    *,
    title: str,
    deadline,
    status: ReportStatus,
    group_id=None,
    submitted_at: datetime | None = None,
) -> tuple[Report, Internship, ReportVersion | None]:
    internship = Internship(
        organization_id=org.org.id,
        group_id=group_id or org.group.id,
        template_version_id=org.template_version.id,
        created_by_teacher_id=org.teacher.id,
        title=title,
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
        status=status,
        document_data={},
    )
    db.add(report)
    db.flush()
    version = None
    if submitted_at is not None:
        version = ReportVersion(
            report_id=report.id,
            version_number=1,
            document_data={},
            submitted_at=submitted_at,
        )
        db.add(version)
        db.flush()
        report.current_version_id = version.id
    db.commit()
    return report, internship, version


def test_teacher_review_queue_filters_and_exposes_review_metadata(client, db, org_a: OrgFixture):
    today = datetime.now(timezone.utc).date()
    report, internship, version = _add_queue_report(
        db,
        org_a,
        title="Target practice",
        deadline=today - timedelta(days=1),
        status=ReportStatus.SUBMITTED,
        submitted_at=datetime.now(timezone.utc),
    )
    assert version is not None
    db.add(
        Comment(
            organization_id=org_a.org.id,
            report_id=report.id,
            report_version_id=version.id,
            author_user_id=org_a.teacher_user.id,
            is_general=True,
            body="Check the conclusion.",
            status=CommentStatus.OPEN,
        )
    )
    _add_queue_report(
        db,
        org_a,
        title="Other practice",
        deadline=today + timedelta(days=10),
        status=ReportStatus.SUBMITTED,
        submitted_at=datetime.now(timezone.utc),
    )
    db.commit()

    response = client.get(
        f"/api/v1/groups/{org_a.group.id}/reports/queue",
        params={
            "status": "SUBMITTED",
            "internship_id": str(internship.id),
            "deadline": "overdue",
            "student": "Test Student",
        },
        headers=auth_headers(org_a.teacher_token(client)),
    )

    assert response.status_code == 200
    assert response.headers["X-Total-Count"] == "1"
    item = response.json()[0]
    assert item["id"] == str(report.id)
    assert item["internship_id"] == str(internship.id)
    assert item["student_id"] == str(org_a.student.id)
    assert item["status"] == "SUBMITTED"
    assert item["current_version_id"] == str(version.id)
    assert item["student_name"] == "Test Student"
    assert item["internship_title"] == "Target practice"
    assert item["deadline"] == (today - timedelta(days=1)).isoformat()
    assert item["is_overdue"] is True
    assert item["submitted_late"] is True
    assert item["open_comments_count"] == 1


def test_review_queue_orders_overdue_then_waiting_review_then_deadline_and_returns_next(client, db, org_a: OrgFixture):
    today = datetime.now(timezone.utc).date()
    overdue, _, _ = _add_queue_report(
        db, org_a, title="Overdue draft", deadline=today - timedelta(days=1), status=ReportStatus.DRAFT
    )
    awaiting, _, _ = _add_queue_report(
        db,
        org_a,
        title="Waiting review",
        deadline=today + timedelta(days=20),
        status=ReportStatus.SUBMITTED,
        submitted_at=datetime.now(timezone.utc),
    )
    later, _, _ = _add_queue_report(
        db, org_a, title="Future draft", deadline=today + timedelta(days=1), status=ReportStatus.DRAFT
    )
    token = org_a.teacher_token(client)

    response = client.get(
        f"/api/v1/groups/{org_a.group.id}/reports/queue?limit=2",
        headers=auth_headers(token),
    )
    next_response = client.get(
        f"/api/v1/groups/{org_a.group.id}/reports/{overdue.id}/next-in-queue",
        headers=auth_headers(token),
    )

    assert response.status_code == 200
    assert response.headers["X-Total-Count"] == "3"
    assert response.headers["X-Has-More"] == "true"
    assert [item["id"] for item in response.json()] == [str(overdue.id), str(awaiting.id)]
    assert next_response.status_code == 200
    assert next_response.json()["id"] == str(awaiting.id)
    assert client.get(
        f"/api/v1/groups/{org_a.group.id}/reports/queue?offset=2&limit=2",
        headers=auth_headers(token),
    ).json()[0]["id"] == str(later.id)


def test_review_queue_keeps_teacher_out_of_an_unassigned_group(client, db, org_a: OrgFixture):
    today = datetime.now(timezone.utc).date()
    unassigned_group = Group(organization_id=org_a.org.id, name="UNASSIGNED")
    db.add(unassigned_group)
    db.flush()
    _add_queue_report(
        db,
        org_a,
        title="Private group practice",
        deadline=today,
        status=ReportStatus.SUBMITTED,
        group_id=unassigned_group.id,
        submitted_at=datetime.now(timezone.utc),
    )

    response = client.get(
        f"/api/v1/groups/{unassigned_group.id}/reports/queue",
        headers=auth_headers(org_a.teacher_token(client)),
    )

    assert response.status_code == 403
    assert db.scalar(select(Report).where(Report.organization_id == org_a.org.id)) is not None
