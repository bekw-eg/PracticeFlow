from fastapi import APIRouter, Depends

from app.dependencies.auth import RequestContext, get_current_context
from app.documents.variables import AVAILABLE_VARIABLES
from app.models.enums import RoleName
from app.permissions.rbac import require_role

router = APIRouter(prefix="/variables", tags=["variables"])


@router.get("/catalog")
def variable_catalog(ctx: RequestContext = Depends(get_current_context)) -> list[dict]:
    """Rule 18: the single place variable keys are defined — the frontend's
    'insert variable' picker calls this rather than hardcoding the list."""
    require_role(ctx.role, RoleName.TEACHER)
    return AVAILABLE_VARIABLES
