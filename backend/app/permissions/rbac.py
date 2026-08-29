"""Authorization policy functions.

Kept deliberately separate from services: a service calls these to decide
whether an action is allowed, but never inlines the role/ownership logic
itself. This makes every access rule independently unit-testable and
prevents the same check from being (re)implemented slightly differently
in two different endpoints.
"""
import uuid

from fastapi import HTTPException, status

from app.models.enums import RoleName
from app.repositories.group_repository import GroupRepository


class PermissionDenied(HTTPException):
    def __init__(self, detail: str = "You do not have permission to perform this action."):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def require_role(current_role: str, *allowed: RoleName) -> None:
    if current_role not in {r.value for r in allowed}:
        raise PermissionDenied(f"This action requires one of: {[r.value for r in allowed]}.")


def require_teacher_owns_group(group_repo: GroupRepository, org_id: uuid.UUID, teacher_id: uuid.UUID, group_id: uuid.UUID) -> None:
    if not group_repo.teacher_owns_group(group_repo.db, teacher_id, group_id):
        # Deliberately the same error as "not found" would give — a teacher probing
        # another org's or another teacher's group id should not be able to
        # distinguish "exists but not yours" from "doesn't exist".
        raise PermissionDenied("Group not found or not accessible.")


def require_student_owns_report(report_student_id: uuid.UUID, current_student_id: uuid.UUID) -> None:
    if report_student_id != current_student_id:
        raise PermissionDenied("Report not found or not accessible.")
