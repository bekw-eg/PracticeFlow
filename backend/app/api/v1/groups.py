import uuid

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.pagination import PaginationParams, set_pagination_headers
from app.db.session import get_db
from app.dependencies.auth import RequestContext, get_current_context
from app.models.enums import RoleName
from app.permissions.rbac import require_role
from app.schemas.group import (
    AddGroupMemberRequest,
    BulkStudentOperationRequest,
    BulkStudentOperationResult,
    BulkTransferStudentsRequest,
    GroupDetail,
    GroupMemberOut,
    GroupSummary,
    StudentOptionOut,
)
from app.services.group_service import GroupService

router = APIRouter(prefix="/groups", tags=["groups"])


@router.get("", response_model=list[GroupSummary])
def my_groups(response: Response, page: PaginationParams = Depends(), ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)) -> list[GroupSummary]:
    """'My Groups' — the Teacher's primary landing workspace."""
    require_role(ctx.role, RoleName.TEACHER)
    service = GroupService(db)
    rows = service.my_groups(ctx.organization_id, ctx.teacher_id, page.offset, page.limit)
    set_pagination_headers(response, page, total=service.count_my_groups(ctx.organization_id, ctx.teacher_id), returned=len(rows))
    return [
        GroupSummary(id=r["group"].id, name=r["group"].name, academic_year=r["group"].academic_year, student_count=r["student_count"])
        for r in rows
    ]


@router.get("/{group_id}", response_model=GroupDetail)
def group_detail(
    group_id: uuid.UUID, response: Response, page: PaginationParams = Depends(), ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)
) -> GroupDetail:
    require_role(ctx.role, RoleName.TEACHER)
    result = GroupService(db).group_detail(ctx.organization_id, ctx.teacher_id, group_id, page.offset, page.limit)
    set_pagination_headers(response, page, total=result["members_total"], returned=len(result["members"]))
    group = result["group"]
    students = [
        GroupMemberOut(
            id=m.id,
            student_id=m.student_id,
            full_name=m.student.membership.user.full_name,
            email=m.student.membership.user.email,
        )
        for m in result["members"]
    ]
    return GroupDetail(id=group.id, name=group.name, academic_year=group.academic_year, students=students)


@router.post("/{group_id}/students", response_model=GroupMemberOut, status_code=201)
def add_student(
    group_id: uuid.UUID,
    payload: AddGroupMemberRequest,
    ctx: RequestContext = Depends(get_current_context),
    db: Session = Depends(get_db),
) -> GroupMemberOut:
    require_role(ctx.role, RoleName.TEACHER)
    member = GroupService(db).add_student_to_group(ctx.organization_id, ctx.teacher_id, group_id, payload.student_id, ctx.user_id)
    return GroupMemberOut(
        id=member.id,
        student_id=member.student_id,
        full_name=member.student.membership.user.full_name,
        email=member.student.membership.user.email,
    )


@router.get("/{group_id}/available-students", response_model=list[StudentOptionOut])
def available_students(
    group_id: uuid.UUID,
    response: Response,
    page: PaginationParams = Depends(),
    q: Annotated[str | None, Query(max_length=100)] = None,
    ctx: RequestContext = Depends(get_current_context),
    db: Session = Depends(get_db),
) -> list[StudentOptionOut]:
    require_role(ctx.role, RoleName.TEACHER)
    service = GroupService(db)
    students = service.available_students(ctx.organization_id, ctx.teacher_id, group_id, page.offset, page.limit, q)
    set_pagination_headers(
        response,
        page,
        total=service.count_available_students(ctx.organization_id, ctx.teacher_id, group_id, q),
        returned=len(students),
    )
    return [
        StudentOptionOut(
            id=student.id,
            full_name=student.membership.user.full_name,
            email=student.membership.user.email,
            specialty_name=student.specialty.name if student.specialty else None,
        )
        for student in students
    ]


@router.delete("/{group_id}/students/{student_id}", status_code=204)
def remove_student(group_id: uuid.UUID, student_id: uuid.UUID, ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)) -> None:
    require_role(ctx.role, RoleName.TEACHER)
    GroupService(db).remove_student_from_group(ctx.organization_id, ctx.teacher_id, group_id, student_id, ctx.user_id)


@router.post("/{group_id}/students/bulk-remove", response_model=BulkStudentOperationResult)
def bulk_remove_students(
    group_id: uuid.UUID,
    payload: BulkStudentOperationRequest,
    ctx: RequestContext = Depends(get_current_context),
    db: Session = Depends(get_db),
) -> BulkStudentOperationResult:
    require_role(ctx.role, RoleName.TEACHER)
    return GroupService(db).bulk_remove_students(
        ctx.organization_id, ctx.teacher_id, group_id, payload.student_ids, ctx.user_id
    )


@router.post("/{group_id}/students/{student_id}/transfer/{target_group_id}", response_model=GroupMemberOut)
def transfer_student(
    group_id: uuid.UUID, student_id: uuid.UUID, target_group_id: uuid.UUID, ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)
) -> GroupMemberOut:
    require_role(ctx.role, RoleName.TEACHER)
    member = GroupService(db).transfer_student(ctx.organization_id, ctx.teacher_id, group_id, target_group_id, student_id, ctx.user_id)
    return GroupMemberOut(id=member.id, student_id=member.student_id, full_name=member.student.membership.user.full_name, email=member.student.membership.user.email)


@router.post("/{group_id}/students/bulk-transfer", response_model=BulkStudentOperationResult)
def bulk_transfer_students(
    group_id: uuid.UUID,
    payload: BulkTransferStudentsRequest,
    ctx: RequestContext = Depends(get_current_context),
    db: Session = Depends(get_db),
) -> BulkStudentOperationResult:
    require_role(ctx.role, RoleName.TEACHER)
    return GroupService(db).bulk_transfer_students(
        ctx.organization_id,
        ctx.teacher_id,
        group_id,
        payload.target_group_id,
        payload.student_ids,
        ctx.user_id,
    )
