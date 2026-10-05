import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.pagination import PaginationParams, set_pagination_headers
from app.db.session import get_db
from app.dependencies.auth import RequestContext, get_current_context
from app.dependencies.features import require_legacy_document_editor_enabled
from app.models.enums import RoleName
from app.permissions.rbac import require_role
from app.schemas.internship import CreateInternshipRequest, GroupReportProgress, InternshipOut, UpdateInternshipRequest
from app.services.internship_service import InternshipService

router = APIRouter(tags=["internships"])


@router.get("/groups/{group_id}/internships", response_model=list[InternshipOut])
def list_internships(
    group_id: uuid.UUID, response: Response, page: PaginationParams = Depends(), ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)
) -> list[InternshipOut]:
    require_role(ctx.role, RoleName.TEACHER)
    service = InternshipService(db)
    internships = service.list_for_group(ctx.organization_id, ctx.teacher_id, group_id, page.offset, page.limit)
    set_pagination_headers(response, page, total=service.count_for_group(ctx.organization_id, ctx.teacher_id, group_id), returned=len(internships))
    return [InternshipOut.model_validate(i) for i in internships]


@router.post("/groups/{group_id}/internships", response_model=InternshipOut, status_code=201)
def create_internship(
    group_id: uuid.UUID,
    payload: CreateInternshipRequest,
    ctx: RequestContext = Depends(get_current_context),
    db: Session = Depends(get_db),
    _: None = Depends(require_legacy_document_editor_enabled),
) -> InternshipOut:
    require_role(ctx.role, RoleName.TEACHER)
    internship = InternshipService(db).create(ctx.organization_id, ctx.teacher_id, group_id, ctx.user_id, payload)
    return InternshipOut.model_validate(internship)


@router.post("/internships/{internship_id}/publish", response_model=InternshipOut)
def publish_internship(
    internship_id: uuid.UUID,
    ctx: RequestContext = Depends(get_current_context),
    db: Session = Depends(get_db),
    _: None = Depends(require_legacy_document_editor_enabled),
) -> InternshipOut:
    require_role(ctx.role, RoleName.TEACHER)
    internship = InternshipService(db).publish(ctx.organization_id, ctx.teacher_id, ctx.user_id, internship_id)
    return InternshipOut.model_validate(internship)


@router.patch("/internships/{internship_id}", response_model=InternshipOut)
def update_internship(
    internship_id: uuid.UUID,
    payload: UpdateInternshipRequest,
    ctx: RequestContext = Depends(get_current_context),
    db: Session = Depends(get_db),
    _: None = Depends(require_legacy_document_editor_enabled),
) -> InternshipOut:
    require_role(ctx.role, RoleName.TEACHER)
    return InternshipOut.model_validate(InternshipService(db).update(ctx.organization_id, ctx.teacher_id, ctx.user_id, internship_id, payload))


@router.post("/internships/{internship_id}/close", response_model=InternshipOut)
def close_internship(internship_id: uuid.UUID, ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)) -> InternshipOut:
    require_role(ctx.role, RoleName.TEACHER)
    return InternshipOut.model_validate(InternshipService(db).close(ctx.organization_id, ctx.teacher_id, ctx.user_id, internship_id))


@router.get("/groups/{group_id}/report-progress", response_model=GroupReportProgress)
def report_progress(group_id: uuid.UUID, ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)) -> GroupReportProgress:
    require_role(ctx.role, RoleName.TEACHER)
    return GroupReportProgress(**InternshipService(db).report_progress(ctx.organization_id, ctx.teacher_id, group_id))
