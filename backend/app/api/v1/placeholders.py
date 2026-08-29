"""Foundation-only routes for SUPER_ADMIN and DIRECTOR (rule 3).

Deliberately minimal: authentication + a single placeholder response, proving
the role exists end-to-end (login works, RBAC recognizes it) without any real
business functionality — that's future-phase work and is not stubbed here
with fake data.
"""
from fastapi import APIRouter, Depends

from app.dependencies.auth import RequestContext, get_current_context
from app.models.enums import RoleName
from app.permissions.rbac import require_role

router = APIRouter(tags=["admin-foundation"])


@router.get("/admin/dashboard")
def super_admin_placeholder(ctx: RequestContext = Depends(get_current_context)) -> dict:
    require_role(ctx.role, RoleName.SUPER_ADMIN)
    return {"message": "Super Admin dashboard is not yet implemented in this phase.", "role": ctx.role}


@router.get("/director/dashboard")
def director_placeholder(ctx: RequestContext = Depends(get_current_context)) -> dict:
    require_role(ctx.role, RoleName.DIRECTOR)
    return {"message": "Director dashboard is not yet implemented in this phase.", "role": ctx.role}
