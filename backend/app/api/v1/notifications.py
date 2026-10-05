import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.pagination import PaginationParams, set_pagination_headers
from app.db.session import get_db
from app.dependencies.auth import RequestContext, get_current_context
from app.models.enums import RoleName
from app.schemas.notification import NotificationOut
from app.services.internship_service import InternshipService
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationOut])
def list_notifications(response: Response, page: PaginationParams = Depends(), ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)) -> list[NotificationOut]:
    # Deadline reminders are intentionally materialized only for the current
    # student as the in-app bell polls this endpoint. This preserves tenant and
    # ownership boundaries without adding an external delivery service.
    if ctx.role == RoleName.STUDENT.value:
        InternshipService(db).create_deadline_reminders_for_student(ctx.organization_id, ctx.user_id)
    service = NotificationService(db)
    items = service.list_for_user(ctx.organization_id, ctx.user_id, page.offset, page.limit)
    set_pagination_headers(response, page, total=service.count_for_user(ctx.organization_id, ctx.user_id), returned=len(items))
    return [
        NotificationOut.model_validate(item)
        for item in items
    ]


@router.post("/read-all", status_code=204)
def read_all(ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)) -> None:
    NotificationService(db).mark_read(ctx.organization_id, ctx.user_id)


@router.post("/{notification_id}/read", status_code=204)
def read_one(notification_id: uuid.UUID, ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)) -> None:
    NotificationService(db).mark_read(ctx.organization_id, ctx.user_id, notification_id)
