"""Small administration routes, including the Director's read-only dashboard."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.dependencies.auth import RequestContext, get_current_context
from app.db.session import get_db
from app.models.enums import RoleName
from app.permissions.rbac import require_role
from app.schemas.management import DirectorDashboard
from app.services.management_service import ManagementService

router = APIRouter(tags=["admin-foundation"])


@router.get("/admin/dashboard")
def super_admin_placeholder(ctx: RequestContext = Depends(get_current_context)) -> dict:
    require_role(ctx.role, RoleName.SUPER_ADMIN)
    return {"message": "Super Admin dashboard is not yet implemented in this phase.", "role": ctx.role}


@router.get("/director/dashboard", response_model=DirectorDashboard)
def director_dashboard(
    ctx: RequestContext = Depends(get_current_context),
    db: Session = Depends(get_db),
) -> DirectorDashboard:
    """Tenant-scoped aggregates only; report documents and review data stay private."""
    require_role(ctx.role, RoleName.DIRECTOR)
    return ManagementService(db).director_dashboard(ctx.organization_id)
