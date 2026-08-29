import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.pagination import PaginationParams, set_pagination_headers
from app.db.session import get_db
from app.dependencies.auth import RequestContext, get_current_context
from app.models.enums import RoleName
from app.permissions.rbac import require_role
from app.schemas.comment import (
    CommentOut,
    CommentReplyOut,
    CreateGeneralCommentRequest,
    CreateInlineCommentRequest,
    ReplyRequest,
)
from app.services.comment_service import CommentService

router = APIRouter(tags=["comments"])


def _to_comment_out(entry: dict) -> CommentOut:
    comment = entry["comment"]
    return CommentOut(
        id=comment.id,
        report_version_id=comment.report_version_id,
        author=comment.author,
        is_general=comment.is_general,
        node_id=comment.node_id,
        start_offset=comment.start_offset,
        end_offset=comment.end_offset,
        text_snapshot=comment.text_snapshot,
        body=comment.body,
        status=comment.status.value,
        anchor_status=entry["anchor_status"],
        current_node_text=entry["current_node_text"],
        created_at=comment.created_at,
        resolved_at=comment.resolved_at,
        replies=[CommentReplyOut.model_validate(r) for r in comment.replies],
    )


@router.get("/reports/{report_id}/comments", response_model=list[CommentOut])
def list_comments(
    report_id: uuid.UUID, response: Response, page: PaginationParams = Depends(), ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)
) -> list[CommentOut]:
    require_role(ctx.role, RoleName.TEACHER, RoleName.STUDENT)
    service = CommentService(db)
    entries = service.list_for_report(
        ctx.organization_id, ctx.role, ctx.teacher_id, ctx.student_id, report_id, page.offset, page.limit
    )
    set_pagination_headers(
        response,
        page,
        total=service.count_for_report(ctx.organization_id, ctx.role, ctx.teacher_id, ctx.student_id, report_id),
        returned=len(entries),
    )
    return [_to_comment_out(e) for e in entries]


@router.post("/reports/{report_id}/comments", response_model=CommentOut, status_code=201)
def create_inline_comment(
    report_id: uuid.UUID,
    payload: CreateInlineCommentRequest,
    ctx: RequestContext = Depends(get_current_context),
    db: Session = Depends(get_db),
) -> CommentOut:
    require_role(ctx.role, RoleName.TEACHER)
    service = CommentService(db)
    comment = service.create_inline_comment(
        ctx.organization_id, ctx.teacher_id, ctx.user_id, report_id,
        payload.node_id, payload.start_offset, payload.end_offset, payload.text_snapshot, payload.body,
    )
    entries = service.list_for_report(ctx.organization_id, ctx.role, ctx.teacher_id, ctx.student_id, report_id)
    return _to_comment_out(next(e for e in entries if e["comment"].id == comment.id))


@router.post("/reports/{report_id}/comments/general", response_model=CommentOut, status_code=201)
def create_general_comment(
    report_id: uuid.UUID,
    payload: CreateGeneralCommentRequest,
    ctx: RequestContext = Depends(get_current_context),
    db: Session = Depends(get_db),
) -> CommentOut:
    require_role(ctx.role, RoleName.TEACHER)
    service = CommentService(db)
    comment = service.create_general_comment(ctx.organization_id, ctx.teacher_id, ctx.user_id, report_id, payload.body)
    entries = service.list_for_report(ctx.organization_id, ctx.role, ctx.teacher_id, ctx.student_id, report_id)
    return _to_comment_out(next(e for e in entries if e["comment"].id == comment.id))


@router.post("/reports/{report_id}/comments/{comment_id}/replies", response_model=CommentOut, status_code=201)
def reply_to_comment(
    report_id: uuid.UUID,
    comment_id: uuid.UUID,
    payload: ReplyRequest,
    ctx: RequestContext = Depends(get_current_context),
    db: Session = Depends(get_db),
) -> CommentOut:
    require_role(ctx.role, RoleName.TEACHER, RoleName.STUDENT)
    service = CommentService(db)
    service.reply(ctx.organization_id, ctx.role, ctx.teacher_id, ctx.student_id, ctx.user_id, report_id, comment_id, payload.body)
    entries = service.list_for_report(ctx.organization_id, ctx.role, ctx.teacher_id, ctx.student_id, report_id)
    return _to_comment_out(next(e for e in entries if e["comment"].id == comment_id))


@router.post("/reports/{report_id}/comments/{comment_id}/resolve", response_model=CommentOut)
def resolve_comment(
    report_id: uuid.UUID,
    comment_id: uuid.UUID,
    ctx: RequestContext = Depends(get_current_context),
    db: Session = Depends(get_db),
) -> CommentOut:
    require_role(ctx.role, RoleName.TEACHER)
    service = CommentService(db)
    service.resolve(ctx.organization_id, ctx.teacher_id, ctx.user_id, report_id, comment_id)
    entries = service.list_for_report(ctx.organization_id, ctx.role, ctx.teacher_id, ctx.student_id, report_id)
    return _to_comment_out(next(e for e in entries if e["comment"].id == comment_id))
