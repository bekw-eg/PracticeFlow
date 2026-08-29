import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.documents.numbering import compute_numbering
from app.documents.schemas import Block, DocumentModel
from app.documents.validators import validate_document
from app.documents.variables import resolve_document
from app.models.audit_log import AuditLog
from app.models.enums import AuditEventType, ReportStatus
from app.models.report import Report
from app.models.report_version import ReportVersion
from app.models.teacher import Teacher
from app.models.teacher_group import TeacherGroup
from app.models.membership import OrganizationMembership
from sqlalchemy import select, update
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
            "editable": report.status in EDITABLE_STATUSES,
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
