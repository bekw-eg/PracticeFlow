import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import RequestContext, get_current_context
from app.models.enums import RoleName
from app.permissions.rbac import require_role
from app.schemas.report import ReportOut
from app.schemas.review import RequestRevisionRequest
from app.services.report_review_service import ReportReviewService

router = APIRouter(tags=["review"])


@router.post("/reports/{report_id}/review/start", response_model=ReportOut)
def start_review(
    report_id: uuid.UUID, ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)
) -> ReportOut:
    require_role(ctx.role, RoleName.TEACHER)
    report = ReportReviewService(db).start_review(ctx.organization_id, ctx.teacher_id, ctx.user_id, report_id)
    return ReportOut.model_validate(report)


@router.post("/reports/{report_id}/review/request-revision", response_model=ReportOut)
def request_revision(
    report_id: uuid.UUID,
    payload: RequestRevisionRequest,
    ctx: RequestContext = Depends(get_current_context),
    db: Session = Depends(get_db),
) -> ReportOut:
    require_role(ctx.role, RoleName.TEACHER)
    report = ReportReviewService(db).request_revision(
        ctx.organization_id, ctx.teacher_id, ctx.user_id, report_id, payload.general_comment
    )
    return ReportOut.model_validate(report)


@router.post("/reports/{report_id}/review/approve", response_model=ReportOut)
def approve_report(
    report_id: uuid.UUID, ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)
) -> ReportOut:
    require_role(ctx.role, RoleName.TEACHER)
    report = ReportReviewService(db).approve(ctx.organization_id, ctx.teacher_id, ctx.user_id, report_id)
    return ReportOut.model_validate(report)
