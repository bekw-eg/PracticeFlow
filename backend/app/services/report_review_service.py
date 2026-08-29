"""Report review state machine (rule 2/3): the ONLY place a report's status
transitions during review. Kept deliberately separate from ReportService
(which owns document editing) because these are a different concern -
workflow/authorization/audit, not document content.

Valid transitions (enforced here, nowhere else):

    SUBMITTED        -> UNDER_REVIEW       (start_review, teacher)
    UNDER_REVIEW      -> REVISION_REQUIRED  (request_revision, teacher)
    UNDER_REVIEW      -> APPROVED -> LOCKED (approve, teacher; locking is
                                              an immediate system consequence
                                              of approval, not a separate
                                              manual step - see rule 16/17)
    REVISION_REQUIRED -> SUBMITTED          (resubmit - ReportService.submit(),
                                              reused rather than duplicated;
                                              this service only cares about
                                              the review-side transitions)

No endpoint and no other service sets `report.status` outside of this file
and ReportService.submit() - that is the whole point of centralizing it.
"""
import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.enums import AuditEventType, ReportStatus
from app.models.report import Report
from app.permissions.rbac import require_teacher_owns_group
from app.repositories.group_repository import GroupRepository
from app.repositories.internship_repository import InternshipRepository
from app.repositories.report_repository import ReportRepository
from app.services.audit_service import AuditService
from app.services.comment_service import CommentService
from app.services.notification_service import NotificationService
from app.models.membership import OrganizationMembership
from app.models.student import Student
from sqlalchemy import select


class InvalidReportTransition(HTTPException):
    def __init__(self, current: ReportStatus, action: str):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot {action} a report in status {current.value}.",
        )


class ReportReviewService:
    def __init__(self, db: Session):
        self.db = db
        self.report_repo = ReportRepository(db)
        self.internship_repo = InternshipRepository(db)
        self.group_repo = GroupRepository(db)
        self.audit = AuditService(db)
        self.comments = CommentService(db)
        self.notifications = NotificationService(db)

    def _get_owned_report(self, org_id: uuid.UUID, teacher_id: uuid.UUID, report_id: uuid.UUID) -> Report:
        report = self.report_repo.get(org_id, report_id)
        if report is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
        internship = self.internship_repo.get(org_id, report.internship_id)
        require_teacher_owns_group(self.group_repo, org_id, teacher_id, internship.group_id)
        return report

    def start_review(self, org_id: uuid.UUID, teacher_id: uuid.UUID, actor_user_id: uuid.UUID, report_id: uuid.UUID) -> Report:
        report = self._get_owned_report(org_id, teacher_id, report_id)
        if report.status != ReportStatus.SUBMITTED:
            raise InvalidReportTransition(report.status, "start review on")

        report.status = ReportStatus.UNDER_REVIEW
        self.audit.record(
            organization_id=org_id, actor_user_id=actor_user_id, event_type=AuditEventType.REVIEW_STARTED,
            entity_type="report", entity_id=report.id,
        )
        self.db.commit()
        self.db.refresh(report)
        return report

    def request_revision(
        self, org_id: uuid.UUID, teacher_id: uuid.UUID, actor_user_id: uuid.UUID, report_id: uuid.UUID, general_comment: str | None = None
    ) -> Report:
        report = self._get_owned_report(org_id, teacher_id, report_id)
        if report.status != ReportStatus.UNDER_REVIEW:
            raise InvalidReportTransition(report.status, "request revision on")

        report.status = ReportStatus.REVISION_REQUIRED
        self.audit.record(
            organization_id=org_id, actor_user_id=actor_user_id, event_type=AuditEventType.REPORT_REVISION_REQUESTED,
            entity_type="report", entity_id=report.id,
        )
        self.db.commit()

        # A revision message is naturally just a general comment (rule 19) -
        # created through the same CommentService path as any other general
        # comment, not a separate parallel "message" concept.
        if general_comment:
            self.comments.create_general_comment(org_id, teacher_id, actor_user_id, report.id, general_comment)

        student_user_id = self.db.scalar(select(OrganizationMembership.user_id).join(Student).where(Student.id == report.student_id))
        if student_user_id:
            self.notifications.create(org_id, student_user_id, "REVISION_REQUIRED", "Отчёт возвращён на доработку", general_comment or "Преподаватель запросил доработку отчёта.", f"/reports/{report.id}/edit")
            self.db.commit()

        self.db.refresh(report)
        return report

    def approve(self, org_id: uuid.UUID, teacher_id: uuid.UUID, actor_user_id: uuid.UUID, report_id: uuid.UUID) -> Report:
        report = self._get_owned_report(org_id, teacher_id, report_id)
        if report.status != ReportStatus.UNDER_REVIEW:
            raise InvalidReportTransition(report.status, "approve")

        # Approval and locking happen together, atomically: an APPROVED
        # report that isn't yet LOCKED would be an observable-but-pointless
        # intermediate state (rule 16/17 - locking is a direct system
        # consequence of approval, not a separate teacher action). Both
        # audit events are still recorded distinctly for a complete trail.
        report.status = ReportStatus.APPROVED
        self.audit.record(
            organization_id=org_id, actor_user_id=actor_user_id, event_type=AuditEventType.REPORT_APPROVED,
            entity_type="report", entity_id=report.id,
        )

        report.status = ReportStatus.LOCKED
        self.audit.record(
            organization_id=org_id, actor_user_id=actor_user_id, event_type=AuditEventType.REPORT_LOCKED,
            entity_type="report", entity_id=report.id,
        )

        self.db.commit()
        self.db.refresh(report)
        return report
