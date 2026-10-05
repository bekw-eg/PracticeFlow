import uuid

from fastapi import APIRouter, Depends, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from app.api.pagination import PaginationParams, set_pagination_headers
from app.db.session import get_db
from app.dependencies.auth import RequestContext, get_current_context
from app.models.enums import CheckRuleType
from app.rate_limit.dependencies import get_resource_guard
from app.resource_protection import ResourceGuard
from app.schemas.group_review_report import GroupReportCreate, GroupReportExport, GroupReportListOut, GroupReportOut, GroupReportWrite, ReportFindingOut
from app.services.group_review_report_service import GroupReviewReportService, PPTX_MIME
from app.services.submission_storage import iter_original
from app.storage.base import StorageUnavailableError
from fastapi import HTTPException

router = APIRouter(prefix="/groups/{group_id}/reports", tags=["group-review-reports"])


@router.get("", response_model=list[GroupReportListOut])
def list_reports(group_id: uuid.UUID, response: Response, page: PaginationParams = Depends(),
                 ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)):
    items, total = GroupReviewReportService(db).list(ctx, group_id, page.offset, page.limit)
    set_pagination_headers(response, page, total=total, returned=len(items))
    return items


@router.post("", response_model=GroupReportOut, status_code=201)
def create_report(group_id: uuid.UUID, request: GroupReportCreate,
                  ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)):
    return GroupReviewReportService(db).create(ctx, group_id, request)


@router.get("/{report_id}", response_model=GroupReportOut)
def get_report(group_id: uuid.UUID, report_id: uuid.UUID,
               ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)):
    return GroupReviewReportService(db).get(ctx, group_id, report_id)


@router.put("/{report_id}", response_model=GroupReportOut)
def save_report(group_id: uuid.UUID, report_id: uuid.UUID, request: GroupReportWrite,
                ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)):
    return GroupReviewReportService(db).save(ctx, group_id, report_id, request)


@router.get("/{report_id}/findings", response_model=list[ReportFindingOut])
def report_findings(group_id: uuid.UUID, report_id: uuid.UUID, response: Response, rule_type: CheckRuleType | None = None,
                    page: PaginationParams = Depends(), ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)):
    items, total = GroupReviewReportService(db).findings(ctx, group_id, report_id, page.offset, page.limit, rule_type)
    set_pagination_headers(response, page, total=total, returned=len(items))
    return items


@router.post("/{report_id}/export", response_model=GroupReportOut)
def export_report(group_id: uuid.UUID, report_id: uuid.UUID, request: GroupReportExport,
                  ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db),
                  guard: ResourceGuard = Depends(get_resource_guard)):
    return GroupReviewReportService(db).export(ctx, group_id, report_id, request.revision, guard)


@router.get("/{report_id}/download")
def download_report(group_id: uuid.UUID, report_id: uuid.UUID,
                    ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)):
    service = GroupReviewReportService(db)
    report = service.get(ctx, group_id, report_id)
    if not report.generated_at or not report.storage_key:
        raise HTTPException(409, "Presentation has not been generated")
    try:
        stream = service.storage.open(report.storage_key)
    except FileNotFoundError as exc:
        raise HTTPException(404, "Presentation file is unavailable") from exc
    except StorageUnavailableError as exc:
        raise HTTPException(503, "Private presentation storage is temporarily unavailable") from exc
    return StreamingResponse(iter_original(stream), media_type=PPTX_MIME, background=BackgroundTask(stream.close),
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
                 "Content-Disposition": f'attachment; filename="group-report-{report.id}.pptx"'})
