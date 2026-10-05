import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.documents.numbering import compute_numbering
from app.documents.schemas import Block, DocumentModel
from app.documents.validators import validate_document
from app.documents.variables import resolve_document
from app.models.audit_log import AuditLog
from app.models.comment import Comment
from app.models.enums import AuditEventType, CommentStatus, ReportStatus
from app.models.internship import Internship
from app.models.membership import OrganizationMembership
from app.models.report import Report
from app.models.report_version import ReportVersion
from app.models.student import Student
from app.models.teacher import Teacher
from app.models.teacher_group import TeacherGroup
from app.models.user import User
from sqlalchemy import and_, case, func, or_, select, update
from app.permissions.rbac import require_student_owns_report, require_teacher_owns_group
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.group_repository import GroupRepository
from app.repositories.internship_repository import InternshipRepository
from app.repositories.report_repository import ReportRepository
from app.repositories.report_version_repository import ReportVersionRepository
from app.repositories.template_version_repository import TemplateVersionRepository
from app.services.audit_service import AuditService
from app.services.report_document_context import build_context_for_report
from app.services.notification_service import NotificationService

EDITABLE_STATUSES = (ReportStatus.DRAFT, ReportStatus.REVISION_REQUIRED)
REVIEW_QUEUE_COMPLETED_STATUSES = (ReportStatus.APPROVED, ReportStatus.LOCKED)

STALE_DOCUMENT_REVISION = "STALE_DOCUMENT_REVISION"


def _stale_document_revision() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": STALE_DOCUMENT_REVISION,
            "message": "Document was changed in another tab. Refresh it before saving again.",
        },
    )


class ReportService:
    """Phase 1: student can view their reports and submit.
    Phase 2 adds: reading/editing the working document (rule 15/28/29), with
    variable resolution and numbering applied for display.
    Review/comment/approve/revision TRANSITIONS remain out of scope — Phase 3."""

    def __init__(self, db: Session):
        self.db = db
        self.report_repo = ReportRepository(db)
        self.version_repo = ReportVersionRepository(db)
        self.internship_repo = InternshipRepository(db)
        self.template_version_repo = TemplateVersionRepository(db)
        self.group_repo = GroupRepository(db)
        self.audit = AuditService(db)
        self.notifications = NotificationService(db)

    def list_for_student(
        self, org_id: uuid.UUID, student_id: uuid.UUID, offset: int = 0, limit: int | None = None
    ) -> list[Report]:
        return self.report_repo.list_for_student(org_id, student_id, offset, limit)

    def count_for_student(self, org_id: uuid.UUID, student_id: uuid.UUID) -> int:
        return self.report_repo.count_for_student(org_id, student_id)

    def list_for_group(
        self, org_id: uuid.UUID, teacher_id: uuid.UUID, group_id: uuid.UUID, offset: int = 0, limit: int | None = None
    ) -> list[Report]:
        require_teacher_owns_group(self.group_repo, org_id, teacher_id, group_id)
        return self.report_repo.list_for_group(org_id, group_id, offset, limit)

    def count_for_group(self, org_id: uuid.UUID, teacher_id: uuid.UUID, group_id: uuid.UUID) -> int:
        require_teacher_owns_group(self.group_repo, org_id, teacher_id, group_id)
        return self.report_repo.count_for_group(org_id, group_id)

    def _review_queue_base(
        self,
        org_id: uuid.UUID,
        teacher_id: uuid.UUID,
        group_id: uuid.UUID,
        *,
        status_filter: ReportStatus | None,
        internship_id: uuid.UUID | None,
        deadline_filter: str | None,
        student_query: str | None,
        today: date,
    ):
        """Build the teacher-owned review queue without exposing documents."""
        require_teacher_owns_group(self.group_repo, org_id, teacher_id, group_id)

        open_comments = (
            select(
                Comment.report_id.label("report_id"),
                func.count(Comment.id).label("open_comments_count"),
            )
            .where(
                Comment.organization_id == org_id,
                Comment.status == CommentStatus.OPEN,
                Comment.parent_comment_id.is_(None),
            )
            .group_by(Comment.report_id)
            .subquery()
        )
        overdue_condition = and_(
            Internship.deadline < today,
            Report.status.not_in(REVIEW_QUEUE_COMPLETED_STATUSES),
        )
        submitted_late_condition = and_(
            ReportVersion.submitted_at.is_not(None),
            func.date(ReportVersion.submitted_at) > Internship.deadline,
        )
        statement = (
            select(
                Report.id,
                Report.internship_id,
                Report.student_id,
                Report.status,
                Report.current_version_id,
                Report.created_at,
                User.full_name.label("student_name"),
                Internship.title.label("internship_title"),
                Internship.deadline,
                case((overdue_condition, True), else_=False).label("is_overdue"),
                case((submitted_late_condition, True), else_=False).label("submitted_late"),
                func.coalesce(open_comments.c.open_comments_count, 0).label("open_comments_count"),
                case((overdue_condition, 1), else_=0).label("_overdue_priority"),
                case((Report.status == ReportStatus.SUBMITTED, 1), else_=0).label("_awaiting_review_priority"),
            )
            .join(Internship, Internship.id == Report.internship_id)
            .join(Student, Student.id == Report.student_id)
            .join(OrganizationMembership, OrganizationMembership.id == Student.membership_id)
            .join(User, User.id == OrganizationMembership.user_id)
            .outerjoin(ReportVersion, ReportVersion.id == Report.current_version_id)
            .outerjoin(open_comments, open_comments.c.report_id == Report.id)
            .where(
                Report.organization_id == org_id,
                Internship.organization_id == org_id,
                Internship.group_id == group_id,
                OrganizationMembership.organization_id == org_id,
            )
        )
        if status_filter is not None:
            statement = statement.where(Report.status == status_filter)
        if internship_id is not None:
            statement = statement.where(Internship.id == internship_id)
        if student_query and student_query.strip():
            pattern = f"%{student_query.strip()}%"
            statement = statement.where(or_(User.full_name.ilike(pattern), User.email.ilike(pattern)))
        if deadline_filter == "overdue":
            statement = statement.where(overdue_condition)
        elif deadline_filter == "due_today":
            statement = statement.where(Internship.deadline == today)
        elif deadline_filter == "due_soon":
            statement = statement.where(
                Internship.deadline > today,
                Internship.deadline <= today + timedelta(days=3),
            )
        elif deadline_filter == "upcoming":
            statement = statement.where(Internship.deadline > today + timedelta(days=3))
        return statement

    @staticmethod
    def _review_queue_order(queue):
        return (
            queue.c._overdue_priority.desc(),
            queue.c._awaiting_review_priority.desc(),
            queue.c.deadline.asc(),
            queue.c.created_at.desc(),
            queue.c.id.desc(),
        )

    def list_review_queue(
        self,
        org_id: uuid.UUID,
        teacher_id: uuid.UUID,
        group_id: uuid.UUID,
        *,
        status_filter: ReportStatus | None = None,
        internship_id: uuid.UUID | None = None,
        deadline_filter: str | None = None,
        student_query: str | None = None,
        offset: int = 0,
        limit: int | None = None,
        today: date | None = None,
    ) -> tuple[list[dict], int]:
        queue = self._review_queue_base(
            org_id,
            teacher_id,
            group_id,
            status_filter=status_filter,
            internship_id=internship_id,
            deadline_filter=deadline_filter,
            student_query=student_query,
            today=today or datetime.now(timezone.utc).date(),
        ).subquery()
        total = int(self.db.scalar(select(func.count()).select_from(queue)) or 0)
        statement = select(queue).order_by(*self._review_queue_order(queue)).offset(offset)
        if limit is not None:
            statement = statement.limit(limit)
        return [dict(row) for row in self.db.execute(statement).mappings().all()], total

    def next_review_queue_item(
        self,
        org_id: uuid.UUID,
        teacher_id: uuid.UUID,
        group_id: uuid.UUID,
        report_id: uuid.UUID,
        *,
        status_filter: ReportStatus | None = None,
        internship_id: uuid.UUID | None = None,
        deadline_filter: str | None = None,
        student_query: str | None = None,
        today: date | None = None,
    ) -> dict | None:
        queue = self._review_queue_base(
            org_id,
            teacher_id,
            group_id,
            status_filter=status_filter,
            internship_id=internship_id,
            deadline_filter=deadline_filter,
            student_query=student_query,
            today=today or datetime.now(timezone.utc).date(),
        ).subquery()
        ranked = select(
            queue,
            func.row_number().over(order_by=self._review_queue_order(queue)).label("queue_position"),
        ).subquery()
        current_position = select(ranked.c.queue_position).where(ranked.c.id == report_id).scalar_subquery()
        item = self.db.execute(
            select(ranked).where(ranked.c.queue_position == current_position + 1)
        ).mappings().one_or_none()
        return dict(item) if item is not None else None

    def get_for_student(self, org_id: uuid.UUID, student_id: uuid.UUID, report_id: uuid.UUID) -> Report:
        report = self.report_repo.get(org_id, report_id)
        if report is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
        require_student_owns_report(report.student_id, student_id)
        return report

    def get_for_teacher(self, org_id: uuid.UUID, teacher_id: uuid.UUID, report_id: uuid.UUID) -> Report:
        report = self.report_repo.get(org_id, report_id)
        if report is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
        internship = self.internship_repo.get(org_id, report.internship_id)
        require_teacher_owns_group(self.group_repo, org_id, teacher_id, internship.group_id)
        return report

    def get_history(
        self, org_id: uuid.UUID, role: str, actor_teacher_id: uuid.UUID | None,
        actor_student_id: uuid.UUID | None, report_id: uuid.UUID,
        offset: int = 0, limit: int | None = None,
    ) -> list[AuditLog]:
        """Rule 18: report history panel. Deliberately reuses the existing
        audit log rather than building a parallel history mechanism — every
        lifecycle event (submit, review start, revision request, approve,
        lock) is already recorded there with actor + timestamp."""
        if role == "TEACHER":
            if actor_teacher_id is None:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Teacher profile is not available")
            self.get_for_teacher(org_id, actor_teacher_id, report_id)
        else:
            if actor_student_id is None:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Student profile is not available")
            self.get_for_student(org_id, actor_student_id, report_id)
        return AuditLogRepository(self.db).list_for_entity(org_id, "report", report_id, offset, limit)

    def count_history(
        self, org_id: uuid.UUID, role: str, actor_teacher_id: uuid.UUID | None,
        actor_student_id: uuid.UUID | None, report_id: uuid.UUID,
    ) -> int:
        if role == "TEACHER":
            if actor_teacher_id is None:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Teacher profile is not available")
            self.get_for_teacher(org_id, actor_teacher_id, report_id)
        else:
            if actor_student_id is None:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Student profile is not available")
            self.get_for_student(org_id, actor_student_id, report_id)
        return AuditLogRepository(self.db).count_for_entity(org_id, "report", report_id)

    # ------------------------------------------------------------------
    # Document engine (Phase 2)
    # ------------------------------------------------------------------

    def _resolved_document_and_numbering(self, report: Report) -> tuple[DocumentModel, dict[str, str]]:
        if report.document_data is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Report document has not been initialized yet")
        document = DocumentModel.model_validate(report.document_data)
        internship = self.internship_repo.get(report.organization_id, report.internship_id)
        context = build_context_for_report(self.db, report, internship)
        resolved = resolve_document(document, context)
        numbering = compute_numbering(resolved)
        return resolved, numbering

    def get_document_for_student(self, org_id: uuid.UUID, student_id: uuid.UUID, report_id: uuid.UUID) -> dict:
        report = self.get_for_student(org_id, student_id, report_id)
        document, numbering = self._resolved_document_and_numbering(report)
        return {
            "document": document,
            "numbering": numbering,
            "editable": settings.LEGACY_DOCUMENT_EDITOR_ENABLED and report.status in EDITABLE_STATUSES,
            "revision": report.revision,
        }

    def get_document_for_teacher(self, org_id: uuid.UUID, teacher_id: uuid.UUID, report_id: uuid.UUID) -> dict:
        report = self.get_for_teacher(org_id, teacher_id, report_id)
        document, numbering = self._resolved_document_and_numbering(report)
        # A teacher never edits a student's working document directly.
        return {"document": document, "numbering": numbering, "editable": False, "revision": report.revision}

    def update_document_for_student(
        self,
        org_id: uuid.UUID,
        student_id: uuid.UUID,
        report_id: uuid.UUID,
        expected_revision: int,
        section_updates: dict[str, list[Block]],
    ) -> Report:
        """Rule 15/16: the request shape itself enforces the boundary — a
        student can only ever submit replacement `blocks` for sections keyed
        by id, never the document's meta/titlePage/header/footer/section list.
        Each targeted section is additionally checked for `editable=True`
        before anything is written."""
        report = self.get_for_student(org_id, student_id, report_id)
        if report.status not in EDITABLE_STATUSES:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Report is not currently editable")
        if report.document_data is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Report document has not been initialized yet")

        document = DocumentModel.model_validate(report.document_data)

        for section_id, new_blocks in section_updates.items():
            section = document.find_section(section_id)
            if section is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Section {section_id} not found")
            if not section.editable:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Section '{section.title}' is locked by the template and cannot be edited.",
                )
            section.blocks = new_blocks

        errors = validate_document(document)
        if errors:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail={"errors": errors})

        updated = self.db.execute(
            update(Report)
            .where(
                Report.id == report.id,
                Report.organization_id == org_id,
                Report.student_id == student_id,
                Report.revision == expected_revision,
                Report.status.in_(EDITABLE_STATUSES),
            )
            .values(
                document_data=document.model_dump(mode="json"),
                document_schema_version=document.schema_version,
                revision=Report.revision + 1,
            )
            .returning(Report.id)
        ).scalar_one_or_none()
        if updated is None:
            self.db.rollback()
            raise _stale_document_revision()

        self.db.commit()
        self.db.refresh(report)
        return report

    def submit(self, org_id: uuid.UUID, student_id: uuid.UUID, actor_user_id: uuid.UUID, report_id: uuid.UUID) -> Report:
        report = self.report_repo.get(org_id, report_id)
        if report is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
        require_student_owns_report(report.student_id, student_id)

        if report.status not in EDITABLE_STATUSES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Report is not in a submittable state")
        if report.document_data is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Report document has not been initialized yet")

        document = DocumentModel.model_validate(report.document_data)
        errors = validate_document(document)
        if errors:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail={"errors": errors})

        is_resubmission = report.status == ReportStatus.REVISION_REQUIRED

        # Snapshot the CURRENT WORKING DRAFT (report.document_data), not a
        # fresh copy of the template — this is what actually preserves the
        # student's content across submit/resubmit cycles.
        version = ReportVersion(
            report_id=report.id,
            version_number=self.version_repo.next_version_number(report.id),
            document_data=report.document_data,
            schema_version=report.document_schema_version,
            submitted_at=datetime.now(timezone.utc),
        )
        self.version_repo.add(version)

        report.status = ReportStatus.SUBMITTED
        report.current_version_id = version.id

        self.audit.record(
            organization_id=org_id,
            actor_user_id=actor_user_id,
            event_type=AuditEventType.REPORT_RESUBMITTED if is_resubmission else AuditEventType.REPORT_SUBMITTED,
            entity_type="report",
            entity_id=report.id,
            metadata={"version_number": version.version_number},
        )
        internship = self.internship_repo.get(org_id, report.internship_id)
        teacher_user_ids = self.db.execute(
            select(OrganizationMembership.user_id)
            .join(Teacher, Teacher.membership_id == OrganizationMembership.id)
            .join(TeacherGroup, TeacherGroup.teacher_id == Teacher.id)
            .where(TeacherGroup.group_id == internship.group_id)
        ).scalars().all()
        for teacher_user_id in teacher_user_ids:
            self.notifications.create(org_id, teacher_user_id, "REPORT_SUBMITTED", "Поступил отчёт на проверку", "Студент отправил отчёт по практике.", f"/groups/{internship.group_id}/reports/{report.id}")
        self.db.commit()
        self.db.refresh(report)
        return report
