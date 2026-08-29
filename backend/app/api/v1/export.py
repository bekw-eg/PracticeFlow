import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import RequestContext, get_current_context
from app.export_queue import ExportQueue
from app.models.enums import ExportFormat, ExportJobStatus, RoleName
from app.permissions.rbac import require_role
from app.rate_limit.dependencies import get_export_queue, get_resource_guard
from app.resource_protection import ResourceGuard
from app.schemas.export_job import ExportJobCreated, ExportJobOut
from app.services.export_job_service import ExportJobService, utcnow
from app.storage.base import StorageUnavailableError

router = APIRouter(tags=["export"])


def _out(job) -> ExportJobOut:
    result = ExportJobOut.model_validate(job)
    if job.status == ExportJobStatus.SUCCEEDED:
        result.download_url = f"/api/v1/export-jobs/{job.id}/download"
    return result


@router.post("/reports/{report_id}/exports/{export_format}", status_code=status.HTTP_202_ACCEPTED, response_model=ExportJobCreated)
def create_export(
    report_id: uuid.UUID,
    export_format: ExportFormat,
    ctx: RequestContext = Depends(get_current_context),
    db: Session = Depends(get_db),
    guard: ResourceGuard = Depends(get_resource_guard),
    queue: ExportQueue = Depends(get_export_queue),
) -> ExportJobCreated:
    require_role(ctx.role, RoleName.TEACHER, RoleName.STUDENT)
    job, reused = ExportJobService(db).create(ctx, report_id, export_format, guard, queue)
    return ExportJobCreated(job_id=job.id, status=job.status, reused_active_job=reused)


@router.get("/export-jobs/{job_id}", response_model=ExportJobOut)
def get_export_status(
    job_id: uuid.UUID,
    ctx: RequestContext = Depends(get_current_context),
    db: Session = Depends(get_db),
) -> ExportJobOut:
    require_role(ctx.role, RoleName.TEACHER, RoleName.STUDENT)
    return _out(ExportJobService(db).get_authorized(ctx, job_id))


@router.delete("/export-jobs/{job_id}", response_model=ExportJobOut)
def cancel_export(
    job_id: uuid.UUID,
    ctx: RequestContext = Depends(get_current_context),
    db: Session = Depends(get_db),
) -> ExportJobOut:
    require_role(ctx.role, RoleName.TEACHER, RoleName.STUDENT)
    return _out(ExportJobService(db).cancel(ctx, job_id))


@router.get("/export-jobs/{job_id}/download")
def download_export(
    job_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    ctx: RequestContext = Depends(get_current_context),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    require_role(ctx.role, RoleName.TEACHER, RoleName.STUDENT)
    service = ExportJobService(db)
    job = service.get_authorized(ctx, job_id)
    if job.status != ExportJobStatus.SUCCEEDED or not job.storage_key or not job.content_type:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Export is not ready for download.")
    if job.expires_at and job.expires_at < utcnow():
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Export has expired. Create a new export to download it.")
    try:
        artifact = service.storage.open(job.storage_key)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export file is no longer available.") from exc
    except StorageUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Export storage is temporarily unavailable. Please try again later.",
        ) from exc
    service.record_download(ctx, job)
    export_format = job.format.value if isinstance(job.format, ExportFormat) else job.format
    filename = f"report_{job.report_id}_{datetime.now().strftime('%Y%m%d')}.{export_format}"
    background_tasks.add_task(artifact.close)
    return StreamingResponse(
        artifact,
        media_type=job.content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        background=background_tasks,
    )
