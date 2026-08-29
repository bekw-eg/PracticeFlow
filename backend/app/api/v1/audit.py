import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.pagination import PaginationParams, set_pagination_headers
from app.db.session import get_db
from app.dependencies.auth import RequestContext, get_current_context
from app.models.audit_chain_head import AuditChainHead
from app.models.enums import AuditEventType, RoleName
from app.permissions.rbac import require_role
from app.schemas.audit import AuditEventOut, AuditIntegrityOut
from app.services.audit_service import AuditService

router = APIRouter(prefix="/audit-events", tags=["audit"])


def _audit_access(ctx: RequestContext) -> None:
    # Current organization comes exclusively from the validated membership in
    # the access token. A Super Admin in another organization has no selector
    # here and receives only that other tenant's events.
    require_role(ctx.role, RoleName.SUPER_ADMIN)


def _out(event) -> AuditEventOut:
    return AuditEventOut(
        id=event.id,
        timestamp=event.created_at,
        action=event.event_type,
        actor_user_id=event.actor_user_id,
        target_type=event.entity_type,
        target_id=event.entity_id,
        metadata=event.event_metadata,
        request_id_hash=event.request_id_hash,
        correlation_id_hash=event.correlation_id_hash,
        sequence=event.sequence,
        event_hash=event.event_hash,
    )


@router.get("", response_model=list[AuditEventOut])
def list_audit_events(
    response: Response,
    page: PaginationParams = Depends(),
    occurred_from: datetime | None = Query(default=None, alias="from"),
    occurred_to: datetime | None = Query(default=None, alias="to"),
    action: AuditEventType | None = None,
    actor_id: uuid.UUID | None = None,
    target_type: Annotated[str | None, Query(max_length=100, pattern=r"^[a-z_]+$")] = None,
    target_id: uuid.UUID | None = None,
    ctx: RequestContext = Depends(get_current_context),
    db: Session = Depends(get_db),
) -> list[AuditEventOut]:
    _audit_access(ctx)
    service = AuditService(db)
    items, total = service.list(
        ctx.organization_id,
        offset=page.offset,
        limit=page.limit,
        occurred_from=occurred_from,
        occurred_to=occurred_to,
        action=action,
        actor_user_id=actor_id,
        target_type=target_type,
        target_id=target_id,
    )
    # Audit viewing itself is append-only. The query above is intentionally
    # evaluated first so a view never silently moves its own page boundary.
    service.record(
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user_id,
        event_type=AuditEventType.AUDIT_LOG_VIEWED,
        entity_type="audit_log",
        metadata={"returned": len(items), "filtered": any((occurred_from, occurred_to, action, actor_id, target_type, target_id))},
    )
    db.commit()
    set_pagination_headers(response, page, total=total, returned=len(items))
    return [_out(item) for item in items]


@router.get("/integrity", response_model=AuditIntegrityOut)
def verify_audit_integrity(
    ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)
) -> AuditIntegrityOut:
    _audit_access(ctx)
    service = AuditService(db)
    result = service.verify(ctx.organization_id)
    head = db.get(AuditChainHead, ctx.organization_id)
    service.record(
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user_id,
        event_type=AuditEventType.AUDIT_INTEGRITY_VERIFIED,
        entity_type="audit_log",
        metadata={"valid": result.valid, "checked_events": result.checked_events},
    )
    db.commit()
    return AuditIntegrityOut(
        valid=result.valid,
        checked_events=result.checked_events,
        first_invalid_sequence=result.first_invalid_sequence,
        retention_anchor_sequence=head.retention_anchor_sequence if head else 0,
    )
