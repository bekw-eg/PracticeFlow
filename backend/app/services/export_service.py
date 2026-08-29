"""Export orchestration (rule 34): the only place that connects a report's
data to the DOCX/PDF renderers. Deliberately thin -- fetch, validate,
resolve, render, audit. All actual rendering logic lives in the isolated
renderer packages (rule 22/34: "Do not put generation logic directly
inside route handlers... Use services.").
"""
import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.documents.numbering import compute_numbering
from app.documents.renderers.docx.renderer import render_docx
from app.documents.schemas import DocumentModel
from app.documents.validators import validate_document
from app.documents.variables import resolve_document
from app.models.enums import AuditEventType, ExportFormat
from app.models.export_job import ExportJob
from app.repositories.membership_repository import MembershipRepository
from app.repositories.student_repository import StudentRepository
from app.repositories.teacher_repository import TeacherRepository
from app.repositories.user_repository import UserRepository
from app.repositories.internship_repository import InternshipRepository
from app.services.audit_service import AuditService
from app.services.file_service import FileService
from app.services.report_document_context import build_context_for_report
from app.services.report_service import ReportService


class ExportService:
    def __init__(self, db: Session):
        self.db = db
        self.report_service = ReportService(db)
        self.internship_repo = InternshipRepository(db)
        self.file_service = FileService(db)
        self.audit = AuditService(db)

    def get_authorized_report(self, org_id: uuid.UUID, role: str, actor_teacher_id, actor_student_id, report_id: uuid.UUID):
        if role == "TEACHER":
            return self.report_service.get_for_teacher(org_id, actor_teacher_id, report_id)
        if role == "STUDENT":
            return self.report_service.get_for_student(org_id, actor_student_id, report_id)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only teachers and students can export reports.")

    def _prepare(self, org_id: uuid.UUID, role: str, actor_teacher_id, actor_student_id, report_id: uuid.UUID) -> tuple[DocumentModel, dict]:
        report = self.get_authorized_report(org_id, role, actor_teacher_id, actor_student_id, report_id)

        if report.document_data is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Report has no document content to export yet.")

        document = DocumentModel.model_validate(report.document_data)

        # Rule 44: never generate a corrupt/invalid export.
        errors = validate_document(document)
        if errors:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail={"errors": errors})

        internship = self.internship_repo.get(org_id, report.internship_id)
        context = build_context_for_report(self.db, report, internship)
        resolved = resolve_document(document, context)
        numbering = compute_numbering(resolved)
        return resolved, numbering, report

    def render_docx(self, org_id: uuid.UUID, role: str, actor_teacher_id, actor_student_id, report_id: uuid.UUID) -> bytes:
        resolved, numbering, report = self._prepare(org_id, role, actor_teacher_id, actor_student_id, report_id)

        def load_image(file_id: str) -> bytes:
            data, _content_type = self.file_service.get_bytes(org_id, uuid.UUID(file_id))
            return data

        buffer = render_docx(resolved, numbering, load_image)
        return buffer.read()

    def render_pdf(self, org_id: uuid.UUID, role: str, actor_teacher_id, actor_student_id, report_id: uuid.UUID) -> bytes:
        # WeasyPrint relies on native Pango/Cairo libraries.  Keep this import
        # lazy so a missing optional OS dependency never prevents the API
        # (and DOCX export) from starting.  The production Docker image ships
        # those libraries; a bare local Windows environment receives a useful
        # endpoint-level error instead of a broken server process.
        try:
            from app.documents.renderers.pdf.renderer import render_pdf
        except (ImportError, OSError) as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="PDF export is unavailable because its native rendering dependencies are not installed.",
            ) from exc
        resolved, numbering, report = self._prepare(org_id, role, actor_teacher_id, actor_student_id, report_id)

        def load_image(file_id: str) -> bytes:
            data, _content_type = self.file_service.get_bytes(org_id, uuid.UUID(file_id))
            return data

        buffer = render_pdf(resolved, numbering, load_image)
        return buffer.read()

    def render_for_job(self, job: ExportJob) -> tuple[bytes, str]:
        """Re-authorize a queued request at execution time.

        A durable job does not preserve permission forever: removed memberships,
        deactivated users and role/profile changes all cause the worker to fail
        closed before it opens the source report or its images.
        """
        user = UserRepository(self.db).get_by_id(job.requested_by_user_id)
        membership = MembershipRepository(self.db).get_by_user_and_org(job.requested_by_user_id, job.organization_id)
        if user is None or not user.is_active or membership is None or membership.role.name != job.requested_role:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Export permission is no longer valid.")
        if job.requested_role == "TEACHER":
            teacher = TeacherRepository(self.db).get_by_membership_id(membership.id)
            if teacher is None:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Export permission is no longer valid.")
            actor_teacher_id, actor_student_id = teacher.id, None
        elif job.requested_role == "STUDENT":
            student = StudentRepository(self.db).get_by_membership_id(membership.id)
            if student is None:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Export permission is no longer valid.")
            actor_teacher_id, actor_student_id = None, student.id
        else:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Export permission is no longer valid.")

        if job.format == ExportFormat.DOCX or job.format == ExportFormat.DOCX.value:
            return self.render_docx(job.organization_id, job.requested_role, actor_teacher_id, actor_student_id, job.report_id), (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
        return self.render_pdf(job.organization_id, job.requested_role, actor_teacher_id, actor_student_id, job.report_id), "application/pdf"

    # Legacy service methods remain a small public renderer API for callers
    # outside HTTP. The async job worker uses render_for_job above.
    def export_docx(self, org_id: uuid.UUID, role: str, actor_teacher_id, actor_student_id, actor_user_id: uuid.UUID, report_id: uuid.UUID) -> bytes:
        data = self.render_docx(org_id, role, actor_teacher_id, actor_student_id, report_id)
        self.audit.record(organization_id=org_id, actor_user_id=actor_user_id, event_type=AuditEventType.DOCX_GENERATED, entity_type="report", entity_id=report_id)
        self.db.commit()
        return data

    def export_pdf(self, org_id: uuid.UUID, role: str, actor_teacher_id, actor_student_id, actor_user_id: uuid.UUID, report_id: uuid.UUID) -> bytes:
        data = self.render_pdf(org_id, role, actor_teacher_id, actor_student_id, report_id)
        self.audit.record(organization_id=org_id, actor_user_id=actor_user_id, event_type=AuditEventType.PDF_GENERATED, entity_type="report", entity_id=report_id)
        self.db.commit()
        return data
