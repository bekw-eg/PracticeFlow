from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db
from app.dependencies.auth import RequestContext, get_current_context
from app.models.enums import AuditEventType, RoleName
from app.models.group import Group
from app.models.group_member import GroupMember
from app.models.report import Report
from app.models.student import Student
from app.models.user import User
from app.permissions.rbac import require_role
from app.schemas.profile import StudentProfileGroupOut, StudentProfileOut, UpdateProfileRequest
from app.services.audit_service import AuditService

router = APIRouter(prefix="/profile", tags=["profile"])


def _student_profile(ctx: RequestContext, db: Session) -> Student:
    require_role(ctx.role, RoleName.STUDENT)
    student = db.execute(select(Student).options(joinedload(Student.specialty)).where(Student.id == ctx.student_id)).scalar_one_or_none()
    if student is None:
        raise RuntimeError("Student profile is missing for a student membership")
    return student


@router.get("", response_model=StudentProfileOut)
def get_profile(ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)) -> StudentProfileOut:
    student = _student_profile(ctx, db)
    user = db.get(User, ctx.user_id)
    groups = list(db.execute(
        select(Group).join(GroupMember).where(GroupMember.student_id == student.id, Group.organization_id == ctx.organization_id).order_by(Group.name)
    ).scalars().all())
    reports_count = db.scalar(select(func.count()).select_from(Report).where(Report.organization_id == ctx.organization_id, Report.student_id == student.id)) or 0
    return StudentProfileOut(
        student_id=student.id,
        full_name=user.full_name,
        email=user.email,
        specialty_name=student.specialty.name if student.specialty else None,
        groups=[StudentProfileGroupOut(id=group.id, name=group.name, academic_year=group.academic_year) for group in groups],
        reports_count=reports_count,
    )


@router.patch("", response_model=StudentProfileOut)
def update_profile(payload: UpdateProfileRequest, ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)) -> StudentProfileOut:
    student = _student_profile(ctx, db)
    user = db.get(User, ctx.user_id)
    user.full_name = payload.full_name
    AuditService(db).record(
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user_id,
        event_type=AuditEventType.STUDENT_UPDATED,
        entity_type="student",
        entity_id=student.id,
    )
    db.commit()
    return get_profile(ctx, db)
