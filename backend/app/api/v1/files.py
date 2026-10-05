import uuid

from fastapi import APIRouter, Depends, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import RequestContext, get_current_context
from app.dependencies.features import require_legacy_document_editor_enabled
from app.models.enums import RoleName
from app.permissions.rbac import require_role
from app.rate_limit.dependencies import get_resource_guard
from app.services.file_service import FileService
from app.resource_protection import ResourceGuard

router = APIRouter(prefix="/files", tags=["files"])


@router.post("", status_code=201)
def upload_file(
    file: UploadFile,
    ctx: RequestContext = Depends(get_current_context),
    db: Session = Depends(get_db),
    guard: ResourceGuard = Depends(get_resource_guard),
    _: None = Depends(require_legacy_document_editor_enabled),
) -> dict:
    """Rule 24/25: image upload for the document editor. Any authenticated
    org member (teacher building a template, student adding to their report)
    may upload — tenant scoping happens on the resulting File row, and is
    what get_file() checks on every read."""
    require_role(ctx.role, RoleName.TEACHER, RoleName.STUDENT)
    guard.check_upload_request(ctx.organization_id, ctx.user_id)
    file_row = FileService(db, guard).upload_image(ctx.organization_id, ctx.user_id, file)
    return {
        "id": str(file_row.id),
        "original_filename": file_row.original_filename,
        "content_type": file_row.content_type,
        "size_bytes": file_row.size_bytes,
        "url": f"/api/v1/files/{file_row.id}",
    }


@router.get("/{file_id}")
def get_file(
    file_id: uuid.UUID, ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)
) -> Response:
    require_role(ctx.role, RoleName.TEACHER, RoleName.STUDENT)
    data, content_type = FileService(db).get_bytes(ctx.organization_id, file_id, ctx.user_id)
    return Response(content=data, media_type=content_type)
