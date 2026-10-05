"""Curriculum follows the existing exact Teacher-owner workflow policy."""
from fastapi import HTTPException

from app.dependencies.auth import RequestContext
from app.models.enums import RoleName
from app.permissions.rbac import require_role


def require_curriculum_teacher(ctx: RequestContext) -> None:
    require_role(ctx.role, RoleName.TEACHER)
    if ctx.teacher_id is None:
        raise HTTPException(status_code=404, detail="Discipline not found")
