import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.pagination import PaginationParams, set_pagination_headers
from app.db.session import get_db
from app.dependencies.auth import RequestContext, get_current_context
from app.models.enums import RoleName
from app.models.user import User
from app.permissions.rbac import require_role
from app.schemas.access import AccessLinkOut
from app.schemas.management import (
    AssignTeachersRequest,
    CatalogOut,
    CreateDepartmentRequest,
    CreateGroupRequest,
    CreateMemberRequest,
    CreateOrganizationRequest,
    CreateSpecialtyRequest,
    DepartmentOut,
    ManagementGroupOut,
    ManagementOverview,
    MemberOut,
    OrganizationOut,
    SpecialtyOut,
    UpdateMemberRequest,
)
from app.schemas.mfa import MfaRecoveryRequestOut
from app.services.management_service import ManagementService
from app.services.mfa_service import MfaService

router = APIRouter(prefix="/management", tags=["management"])


def _management_access(ctx: RequestContext) -> None:
    require_role(ctx.role, RoleName.DIRECTOR, RoleName.SUPER_ADMIN)


@router.get("/overview", response_model=ManagementOverview)
def overview(ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)) -> ManagementOverview:
    _management_access(ctx)
    return ManagementOverview.model_validate(ManagementService(db).overview(ctx.organization_id))


@router.get("/members", response_model=list[MemberOut])
def members(
    response: Response,
    page: PaginationParams = Depends(),
    q: Annotated[str | None, Query(max_length=100)] = None,
    ctx: RequestContext = Depends(get_current_context),
    db: Session = Depends(get_db),
) -> list[MemberOut]:
    _management_access(ctx)
    service = ManagementService(db)
    items = service.list_members(ctx.organization_id, page.offset, page.limit, q)
    set_pagination_headers(response, page, total=service.count_members(ctx.organization_id, q), returned=len(items))
    return items


@router.post("/members", response_model=MemberOut, status_code=201)
def create_member(payload: CreateMemberRequest, ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)) -> MemberOut:
    _management_access(ctx)
    return ManagementService(db).create_member(ctx.organization_id, payload, ctx.role, ctx.user_id)


@router.patch("/members/{membership_id}", response_model=MemberOut)
def update_member(membership_id: uuid.UUID, payload: UpdateMemberRequest, ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)) -> MemberOut:
    _management_access(ctx)
    return ManagementService(db).update_member(ctx.organization_id, membership_id, payload, ctx.role, ctx.user_id)


@router.post("/members/{membership_id}/invite", response_model=AccessLinkOut)
def invite_member(membership_id: uuid.UUID, ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)) -> AccessLinkOut:
    _management_access(ctx)
    return AccessLinkOut.model_validate(
        ManagementService(db).create_access_link(ctx.organization_id, membership_id, "INVITE", ctx.role, ctx.user_id)
    )


@router.post("/members/{membership_id}/password-reset", response_model=AccessLinkOut)
def reset_member_password(membership_id: uuid.UUID, ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)) -> AccessLinkOut:
    _management_access(ctx)
    return AccessLinkOut.model_validate(
        ManagementService(db).create_access_link(ctx.organization_id, membership_id, "PASSWORD_RESET", ctx.role, ctx.user_id)
    )


@router.get("/groups", response_model=list[ManagementGroupOut])
def groups(response: Response, page: PaginationParams = Depends(), ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)) -> list[ManagementGroupOut]:
    _management_access(ctx)
    service = ManagementService(db)
    items = service.list_groups(ctx.organization_id, page.offset, page.limit)
    set_pagination_headers(response, page, total=service.count_groups(ctx.organization_id), returned=len(items))
    return items


@router.post("/groups", response_model=ManagementGroupOut, status_code=201)
def create_group(payload: CreateGroupRequest, ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)) -> ManagementGroupOut:
    _management_access(ctx)
    return ManagementService(db).create_group(ctx.organization_id, payload, ctx.user_id)


@router.post("/groups/{group_id}/teachers", response_model=ManagementGroupOut)
def assign_teachers(
    group_id: uuid.UUID, payload: AssignTeachersRequest, ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)
) -> ManagementGroupOut:
    _management_access(ctx)
    return ManagementService(db).assign_teachers(ctx.organization_id, group_id, payload.teacher_ids, ctx.user_id)


@router.delete("/groups/{group_id}/teachers/{teacher_id}", status_code=204)
def remove_teacher(group_id: uuid.UUID, teacher_id: uuid.UUID, ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)) -> None:
    _management_access(ctx)
    ManagementService(db).remove_teacher(ctx.organization_id, group_id, teacher_id, ctx.user_id)


@router.get("/catalog", response_model=CatalogOut)
def catalog(ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)) -> CatalogOut:
    _management_access(ctx)
    return CatalogOut.model_validate(ManagementService(db).catalog(ctx.organization_id))


@router.post("/departments", response_model=DepartmentOut, status_code=201)
def create_department(payload: CreateDepartmentRequest, ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)) -> DepartmentOut:
    _management_access(ctx)
    return DepartmentOut.model_validate(ManagementService(db).create_department(ctx.organization_id, payload.name, ctx.user_id))


@router.post("/specialties", response_model=SpecialtyOut, status_code=201)
def create_specialty(payload: CreateSpecialtyRequest, ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)) -> SpecialtyOut:
    _management_access(ctx)
    return SpecialtyOut.model_validate(ManagementService(db).create_specialty(ctx.organization_id, payload.department_id, payload.name, payload.code, ctx.user_id))


@router.get("/organizations", response_model=list[OrganizationOut])
def organizations(response: Response, page: PaginationParams = Depends(), ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)) -> list[OrganizationOut]:
    require_role(ctx.role, RoleName.SUPER_ADMIN)
    service = ManagementService(db)
    items = service.list_organizations(page.offset, page.limit)
    set_pagination_headers(response, page, total=service.count_organizations(), returned=len(items))
    return [OrganizationOut.model_validate(org) for org in items]


@router.post("/organizations", response_model=OrganizationOut, status_code=201)
def create_organization(
    payload: CreateOrganizationRequest, ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)
) -> OrganizationOut:
    require_role(ctx.role, RoleName.SUPER_ADMIN)
    return OrganizationOut.model_validate(ManagementService(db).create_organization(payload.name, payload.slug, ctx.user_id))


@router.get("/mfa-recovery-requests", response_model=list[MfaRecoveryRequestOut])
def mfa_recovery_requests(
    ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)
) -> list[MfaRecoveryRequestOut]:
    require_role(ctx.role, RoleName.SUPER_ADMIN)
    requests = MfaService(db).list_peer_recovery_requests(ctx.organization_id)
    result: list[MfaRecoveryRequestOut] = []
    for item in requests:
        user = db.get(User, item.user_id)
        if user:
            result.append(MfaRecoveryRequestOut(
                id=item.id,
                user_id=user.id,
                user_email=user.email,
                user_name=user.full_name,
                expires_at=item.expires_at,
                created_at=item.created_at,
            ))
    return result


@router.post("/mfa-recovery-requests/{challenge_id}/approve", status_code=204)
def approve_mfa_recovery_request(
    challenge_id: uuid.UUID,
    ctx: RequestContext = Depends(get_current_context),
    db: Session = Depends(get_db),
) -> None:
    require_role(ctx.role, RoleName.SUPER_ADMIN)
    MfaService(db).approve_peer_recovery(challenge_id, ctx.organization_id, ctx.user_id)
