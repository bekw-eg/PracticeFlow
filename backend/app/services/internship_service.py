import uuid
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import AuditEventType, InternshipStatus, ReportStatus
from app.models.internship import Internship
from app.models.membership import OrganizationMembership
from app.models.report import Report
from app.models.student import Student
from app.permissions.rbac import require_teacher_owns_group
from app.repositories.group_member_repository import GroupMemberRepository
from app.repositories.group_repository import GroupRepository
from app.repositories.internship_repository import InternshipRepository
from app.repositories.report_repository import ReportRepository
from app.repositories.template_version_repository import TemplateVersionRepository
from app.schemas.internship import CreateInternshipRequest, UpdateInternshipRequest
from app.services.notification_service import NotificationService
from app.services.audit_service import AuditService


_DEADLINE_REMINDER_DAYS = 3
_DEADLINE_REMINDER_TITLES = {
    "REPORT_DEADLINE_SOON": "Скоро срок сдачи отчёта",
    "REPORT_DEADLINE_TODAY": "Срок сдачи отчёта — сегодня",
    "REPORT_DEADLINE_OVERDUE": "Срок сдачи отчёта истёк",
}


class InternshipService:
    def __init__(self, db: Session):
        self.db = db
        self.group_repo = GroupRepository(db)
        self.member_repo = GroupMemberRepository(db)
        self.internship_repo = InternshipRepository(db)
        self.version_repo = TemplateVersionRepository(db)
        self.report_repo = ReportRepository(db)
        self.audit = AuditService(db)
        self.notifications = NotificationService(db)

    def list_for_group(
        self, org_id: uuid.UUID, teacher_id: uuid.UUID, group_id: uuid.UUID, offset: int = 0, limit: int | None = None
    ) -> list[Internship]:
        require_teacher_owns_group(self.group_repo, org_id, teacher_id, group_id)
        return self.internship_repo.list_for_group(org_id, group_id, offset, limit)

    def count_for_group(self, org_id: uuid.UUID, teacher_id: uuid.UUID, group_id: uuid.UUID) -> int:
        require_teacher_owns_group(self.group_repo, org_id, teacher_id, group_id)
        return self.internship_repo.count_for_group(org_id, group_id)

    def create(
        self, org_id: uuid.UUID, teacher_id: uuid.UUID, group_id: uuid.UUID, actor_user_id: uuid.UUID, payload: CreateInternshipRequest
    ) -> Internship:
        require_teacher_owns_group(self.group_repo, org_id, teacher_id, group_id)

        # The template version is fixed here, permanently (rule 9) — this
        # internship will never silently pick up a later version.
        version = self.version_repo.get(org_id, payload.template_version_id)
        if version is None or not version.is_published:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Template version not found or not published")

        internship = Internship(
            organization_id=org_id,
            group_id=group_id,
            template_version_id=payload.template_version_id,
            created_by_teacher_id=teacher_id,
            title=payload.title,
            description=payload.description,
            specialty_id=payload.specialty_id,
            start_date=payload.start_date,
            end_date=payload.end_date,
            deadline=payload.deadline,
            status=InternshipStatus.DRAFT,
        )
        self.internship_repo.add(internship)
        self.audit.record(
            organization_id=org_id,
            actor_user_id=actor_user_id,
            event_type=AuditEventType.INTERNSHIP_CREATED,
            entity_type="internship",
            entity_id=internship.id,
        )
        self.db.commit()
        self.db.refresh(internship)
        return internship

    def update(self, org_id: uuid.UUID, teacher_id: uuid.UUID, actor_user_id: uuid.UUID, internship_id: uuid.UUID, payload: UpdateInternshipRequest) -> Internship:
        internship = self.internship_repo.get(org_id, internship_id)
        if internship is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Internship not found")
        require_teacher_owns_group(self.group_repo, org_id, teacher_id, internship.group_id)
        if internship.status != InternshipStatus.DRAFT:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only a draft internship can be edited")
        for field in ("title", "description", "start_date", "end_date", "deadline"):
            value = getattr(payload, field)
            if value is not None:
                setattr(internship, field, value)
        if internship.end_date < internship.start_date or internship.deadline < internship.start_date:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Dates are inconsistent")
        self.db.commit()
        self.db.refresh(internship)
        return internship

    def publish(self, org_id: uuid.UUID, teacher_id: uuid.UUID, actor_user_id: uuid.UUID, internship_id: uuid.UUID) -> Internship:
        internship = self.internship_repo.get(org_id, internship_id)
        if internship is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Internship not found")
        require_teacher_owns_group(self.group_repo, org_id, teacher_id, internship.group_id)

        if internship.status != InternshipStatus.DRAFT:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only a DRAFT internship can be published")

        internship.status = InternshipStatus.PUBLISHED

        # Every current member of the group receives the internship, i.e. gets
        # a DRAFT report row created for them now (rule 21) — not lazily on
        # first login, so a teacher's group roster and report roster stay in sync.
        # Each report's document_data is its OWN deep copy of the fixed
        # template version's content (rule 29/30) — editing one student's
        # report, or even a later template version, never touches another
        # student's document or the template itself.
        template_version = self.version_repo.get(org_id, internship.template_version_id)
        members = self.member_repo.list_for_group(org_id, internship.group_id)
        for member in members:
            existing = self.report_repo.get_for_internship_and_student(org_id, internship.id, member.student_id)
            if existing is None:
                self.report_repo.add(
                    Report(
                        organization_id=org_id,
                        internship_id=internship.id,
                        student_id=member.student_id,
                        document_data=deepcopy(template_version.document_data),
                        document_schema_version=template_version.schema_version,
                    )
                )
            self.notifications.create(org_id, member.student.membership.user_id, "PRACTICE_ASSIGNED", "Вам назначена практика", internship.title, "/reports")

        self.audit.record(
            organization_id=org_id,
            actor_user_id=actor_user_id,
            event_type=AuditEventType.INTERNSHIP_PUBLISHED,
            entity_type="internship",
            entity_id=internship.id,
            metadata={"student_count": len(members)},
        )
        self.db.commit()
        self.db.refresh(internship)
        return internship

    def close(self, org_id: uuid.UUID, teacher_id: uuid.UUID, actor_user_id: uuid.UUID, internship_id: uuid.UUID) -> Internship:
        internship = self.internship_repo.get(org_id, internship_id)
        if internship is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Internship not found")
        require_teacher_owns_group(self.group_repo, org_id, teacher_id, internship.group_id)
        if internship.status != InternshipStatus.PUBLISHED:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only a published internship can be closed")
        internship.status = InternshipStatus.CLOSED
        self.db.commit()
        self.db.refresh(internship)
        return internship

    @staticmethod
    def deadline_reminder_type(deadline: date, *, today: date) -> str | None:
        """Return the one reminder stage applicable to a report today.

        A student who first opens the app during the three-day window still
        gets the early reminder, while a later visit gets only the currently
        relevant deadline or overdue stage rather than stale notifications.
        """
        if deadline - timedelta(days=_DEADLINE_REMINDER_DAYS) <= today < deadline:
            return "REPORT_DEADLINE_SOON"
        if today == deadline:
            return "REPORT_DEADLINE_TODAY"
        if today > deadline:
            return "REPORT_DEADLINE_OVERDUE"
        return None

    def create_deadline_reminders_for_student(
        self, org_id: uuid.UUID, user_id: uuid.UUID, *, now: datetime | None = None
    ) -> int:
        """Materialize current deadline reminders for one authenticated student.

        NotificationBell polls the scoped notifications endpoint, so reminders
        remain in-app only and do not require an email provider or a global
        scheduler. Deadline dates are evaluated in UTC, matching the rest of
        the API's date-based deadline handling.
        """
        instant = now or datetime.now(timezone.utc)
        if instant.tzinfo is None:
            raise ValueError("deadline reminder time must be timezone-aware")
        today = instant.astimezone(timezone.utc).date()
        rows = self.db.execute(
            select(Report.id, Internship.title, Internship.deadline)
            .join(Internship, Internship.id == Report.internship_id)
            .join(Student, Student.id == Report.student_id)
            .join(OrganizationMembership, OrganizationMembership.id == Student.membership_id)
            .where(
                Report.organization_id == org_id,
                Internship.organization_id == org_id,
                OrganizationMembership.organization_id == org_id,
                OrganizationMembership.user_id == user_id,
                OrganizationMembership.is_active.is_(True),
                Internship.status == InternshipStatus.PUBLISHED,
                Report.status.in_((ReportStatus.DRAFT, ReportStatus.REVISION_REQUIRED)),
            )
        ).all()

        created = 0
        for report_id, internship_title, deadline in rows:
            reminder_type = self.deadline_reminder_type(deadline, today=today)
            if reminder_type is None:
                continue
            _, was_created = self.notifications.create_once(
                org_id,
                user_id,
                reminder_type,
                _DEADLINE_REMINDER_TITLES[reminder_type],
                body=internship_title,
                link=f"/reports/{report_id}/edit",
                dedupe_key=f"report-deadline:{report_id}:{reminder_type}",
            )
            created += int(was_created)

        if created:
            self.db.commit()
        return created

    def report_progress(self, org_id: uuid.UUID, teacher_id: uuid.UUID, group_id: uuid.UUID) -> dict:
        require_teacher_owns_group(self.group_repo, org_id, teacher_id, group_id)
        reports = self.report_repo.list_for_group(org_id, group_id)
        counts = {"total": len(reports), "draft": 0, "submitted": 0, "under_review": 0, "revision_required": 0, "locked": 0}
        for report in reports:
            if report.status == ReportStatus.DRAFT:
                counts["draft"] += 1
            elif report.status == ReportStatus.SUBMITTED:
                counts["submitted"] += 1
            elif report.status == ReportStatus.UNDER_REVIEW:
                counts["under_review"] += 1
            elif report.status == ReportStatus.REVISION_REQUIRED:
                counts["revision_required"] += 1
            elif report.status in {ReportStatus.LOCKED, ReportStatus.APPROVED}:
                counts["locked"] += 1
        return counts
