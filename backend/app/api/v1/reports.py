import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.pagination import PaginationParams, set_pagination_headers
from app.db.session import get_db
from app.dependencies.auth import RequestContext, get_current_context
from app.models.enums import RoleName
from app.permissions.rbac import require_role
from app.repositories.internship_repository import InternshipRepository
from app.repositories.report_version_repository import ReportVersionRepository
from app.schemas.report import (
    ReportDetail,
    ReportDocumentResponse,
    ReportHistoryEntry,
    ReportOut,
    ReportVersionOut,
    UpdateReportDocumentRequest,
)
from app.services.report_service import ReportService

router = APIRouter(tags=["reports"])


@router.get("/reports", response_model=list[ReportOut])
def my_reports(response: Response, page: PaginationParams = Depends(), ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)) -> list[ReportOut]:
    require_role(ctx.role, RoleName.STUDENT)
    service = ReportService(db)
    reports = service.list_for_student(ctx.organization_id, ctx.student_id, page.offset, page.limit)
    set_pagination_headers(response, page, total=service.count_for_student(ctx.organization_id, ctx.student_id), returned=len(reports))
    return [ReportOut.model_validate(r) for r in reports]


@router.get("/reports/{report_id}", response_model=ReportDetail)
def report_detail(
    report_id: uuid.UUID, response: Response, page: PaginationParams = Depends(), ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)
) -> ReportDetail:
    """Rule 5/38: both the reviewing teacher and the owning student can read
    a report's detail — ownership/authorization differs per role but the
    shape of the response doesn't."""
    require_role(ctx.role, RoleName.TEACHER, RoleName.STUDENT)
    service = ReportService(db)
    if ctx.role == "STUDENT":
        report = service.get_for_student(ctx.organization_id, ctx.student_id, report_id)
    else:
        report = service.get_for_teacher(ctx.organization_id, ctx.teacher_id, report_id)

    internship = InternshipRepository(db).get(ctx.organization_id, report.internship_id)
    versions_repo = ReportVersionRepository(db)
    versions = versions_repo.list_for_report(report.id, page.offset, page.limit)
    set_pagination_headers(response, page, total=versions_repo.count_for_report(report.id), returned=len(versions))
    return ReportDetail(
        id=report.id,
        internship_id=report.internship_id,
        student_id=report.student_id,
        status=report.status,
        current_version_id=report.current_version_id,
        created_at=report.created_at,
        deadline=internship.deadline.isoformat(),
        versions=[
            ReportVersionOut(
                id=v.id, version_number=v.version_number, submitted_at=v.submitted_at,
                is_late=v.submitted_at.date() > internship.deadline,
            )
            for v in versions
        ],
    )


@router.get("/reports/{report_id}/history", response_model=list[ReportHistoryEntry])
def report_history(
    report_id: uuid.UUID, response: Response, page: PaginationParams = Depends(), ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)
) -> list[ReportHistoryEntry]:
    require_role(ctx.role, RoleName.TEACHER, RoleName.STUDENT)
    service = ReportService(db)
    entries = service.get_history(
        ctx.organization_id, ctx.role, ctx.teacher_id, ctx.student_id, report_id, page.offset, page.limit
    )
    set_pagination_headers(
        response,
        page,
        total=service.count_history(ctx.organization_id, ctx.role, ctx.teacher_id, ctx.student_id, report_id),
        returned=len(entries),
    )
    return [
        ReportHistoryEntry(
            event=e.event_type.value,
            actor_name=e.actor.full_name if e.actor else None,
            actor_role=None,
            created_at=e.created_at,
            metadata=e.event_metadata,
        )
        for e in entries
    ]


@router.get("/reports/{report_id}/document", response_model=ReportDocumentResponse)
def get_report_document(
    report_id: uuid.UUID, ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)
) -> ReportDocumentResponse:
    """Rule 15/28: same underlying document engine for both roles — a
    Teacher gets a read-only resolved view (via a group they own), a Student
    gets their own editable working draft, with variables resolved either way."""
    require_role(ctx.role, RoleName.TEACHER, RoleName.STUDENT)
    service = ReportService(db)
    if ctx.role == "STUDENT":
        result = service.get_document_for_student(ctx.organization_id, ctx.student_id, report_id)
    else:
        result = service.get_document_for_teacher(ctx.organization_id, ctx.teacher_id, report_id)
    return ReportDocumentResponse(**result)


@router.patch("/reports/{report_id}/document", response_model=ReportDocumentResponse)
def update_report_document(
    report_id: uuid.UUID,
    payload: UpdateReportDocumentRequest,
    ctx: RequestContext = Depends(get_current_context),
    db: Session = Depends(get_db),
) -> ReportDocumentResponse:
    require_role(ctx.role, RoleName.STUDENT)
    service = ReportService(db)
    service.update_document_for_student(
        ctx.organization_id,
        ctx.student_id,
        report_id,
        payload.expected_revision,
        payload.sections,
    )
    result = service.get_document_for_student(ctx.organization_id, ctx.student_id, report_id)
    return ReportDocumentResponse(**result)


@router.post("/reports/{report_id}/submit", response_model=ReportOut)
def submit_report(
    report_id: uuid.UUID, ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)
) -> ReportOut:
    require_role(ctx.role, RoleName.STUDENT)
    report = ReportService(db).submit(ctx.organization_id, ctx.student_id, ctx.user_id, report_id)
    return ReportOut.model_validate(report)


@router.get("/groups/{group_id}/reports", response_model=list[ReportOut])
def group_reports(
    group_id: uuid.UUID, response: Response, page: PaginationParams = Depends(), ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)
) -> list[ReportOut]:
    require_role(ctx.role, RoleName.TEACHER)
    service = ReportService(db)
    reports = service.list_for_group(ctx.organization_id, ctx.teacher_id, group_id, page.offset, page.limit)
    set_pagination_headers(response, page, total=service.count_for_group(ctx.organization_id, ctx.teacher_id, group_id), returned=len(reports))
    return [ReportOut.model_validate(r) for r in reports]
