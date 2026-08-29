import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.group_member import GroupMember
from app.models.enums import AuditEventType
from app.models.membership import OrganizationMembership
from app.models.student import Student
from app.models.user import User
from sqlalchemy import func, or_, select
from sqlalchemy.orm import joinedload
from app.permissions.rbac import require_teacher_owns_group
from app.repositories.group_member_repository import GroupMemberRepository
from app.repositories.group_repository import GroupRepository
from app.repositories.student_repository import StudentRepository
from app.services.audit_service import AuditService


class GroupService:
    """Backs the Teacher's group-centric workspace: My Groups -> group detail.

    Every method here requires a teacher_id and enforces group ownership —
    there is no path in this service that returns a group a teacher doesn't
    explicitly own, even within the correct organization.
    """

    def __init__(self, db: Session):
        self.db = db
        self.group_repo = GroupRepository(db)
        self.member_repo = GroupMemberRepository(db)
        self.student_repo = StudentRepository(db)
        self.audit = AuditService(db)

    def my_groups(self, org_id: uuid.UUID, teacher_id: uuid.UUID, offset: int = 0, limit: int | None = None) -> list[dict]:
        groups = self.group_repo.list_for_teacher(org_id, teacher_id, offset, limit)
        result = []
        for group in groups:
            result.append({"group": group, "student_count": self.member_repo.count_for_group(org_id, group.id)})
        return result

    def count_my_groups(self, org_id: uuid.UUID, teacher_id: uuid.UUID) -> int:
        return self.group_repo.count_for_teacher(org_id, teacher_id)

    def group_detail(
        self, org_id: uuid.UUID, teacher_id: uuid.UUID, group_id: uuid.UUID, offset: int = 0, limit: int | None = None
    ) -> dict:
        require_teacher_owns_group(self.group_repo, org_id, teacher_id, group_id)
        group = self.group_repo.get(org_id, group_id)
        if group is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
        members = self.member_repo.list_for_group(org_id, group_id, offset, limit)
        return {"group": group, "members": members, "members_total": self.member_repo.count_for_group(org_id, group_id)}

    def add_student_to_group(
        self, org_id: uuid.UUID, teacher_id: uuid.UUID, group_id: uuid.UUID, student_id: uuid.UUID,
        actor_user_id: uuid.UUID | None = None,
    ) -> GroupMember:
        require_teacher_owns_group(self.group_repo, org_id, teacher_id, group_id)
        student = self.student_repo.get_by_id(org_id, student_id)
        if student is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
        if self.member_repo.exists(group_id, student_id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Student already in group")
        member = self.member_repo.add(GroupMember(group_id=group_id, student_id=student_id))
        self.audit.record(
            organization_id=org_id, actor_user_id=actor_user_id,
            event_type=AuditEventType.STUDENT_UPDATED, entity_type="student", entity_id=student_id,
            metadata={"group_membership_changed": True},
        )
        self.db.commit()
        return member

    def available_students(
        self,
        org_id: uuid.UUID,
        teacher_id: uuid.UUID,
        group_id: uuid.UUID,
        offset: int = 0,
        limit: int | None = None,
        q: str | None = None,
    ) -> list[Student]:
        """Students from the teacher's organization not already enrolled in this group."""
        require_teacher_owns_group(self.group_repo, org_id, teacher_id, group_id)
        enrolled = select(GroupMember.student_id).where(GroupMember.group_id == group_id)
        stmt = (
            select(Student)
            .join(OrganizationMembership, Student.membership_id == OrganizationMembership.id)
            .join(User, OrganizationMembership.user_id == User.id)
            .options(joinedload(Student.membership).joinedload(OrganizationMembership.user), joinedload(Student.specialty))
            .where(OrganizationMembership.organization_id == org_id, ~Student.id.in_(enrolled))
            .order_by(User.full_name, User.email, Student.id)
        )
        if q:
            term = f"%{q}%"
            stmt = stmt.where(or_(User.full_name.ilike(term), User.email.ilike(term)))
        stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.db.execute(stmt).unique().scalars().all())

    def count_available_students(
        self, org_id: uuid.UUID, teacher_id: uuid.UUID, group_id: uuid.UUID, q: str | None = None
    ) -> int:
        require_teacher_owns_group(self.group_repo, org_id, teacher_id, group_id)
        enrolled = select(GroupMember.student_id).where(GroupMember.group_id == group_id)
        stmt = (
            select(func.count())
            .select_from(Student)
            .join(OrganizationMembership, Student.membership_id == OrganizationMembership.id)
            .join(User, OrganizationMembership.user_id == User.id)
            .where(OrganizationMembership.organization_id == org_id, ~Student.id.in_(enrolled))
        )
        if q:
            term = f"%{q}%"
            stmt = stmt.where(or_(User.full_name.ilike(term), User.email.ilike(term)))
        return int(self.db.scalar(stmt) or 0)

    def remove_student_from_group(
        self, org_id: uuid.UUID, teacher_id: uuid.UUID, group_id: uuid.UUID, student_id: uuid.UUID,
        actor_user_id: uuid.UUID | None = None,
    ) -> None:
        require_teacher_owns_group(self.group_repo, org_id, teacher_id, group_id)
        member = self.member_repo.get(org_id, group_id, student_id)
        if member is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student is not a member of this group")
        self.member_repo.delete(member)
        self.audit.record(organization_id=org_id, actor_user_id=actor_user_id, event_type=AuditEventType.STUDENT_UPDATED, entity_type="student", entity_id=student_id, metadata={"group_membership_changed": True})
        self.db.commit()

    def transfer_student(
        self, org_id: uuid.UUID, teacher_id: uuid.UUID, source_group_id: uuid.UUID, target_group_id: uuid.UUID,
        student_id: uuid.UUID, actor_user_id: uuid.UUID | None = None,
    ) -> GroupMember:
        require_teacher_owns_group(self.group_repo, org_id, teacher_id, source_group_id)
        require_teacher_owns_group(self.group_repo, org_id, teacher_id, target_group_id)
        member = self.member_repo.get(org_id, source_group_id, student_id)
        if member is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student is not a member of this group")
        if self.member_repo.exists(target_group_id, student_id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Student is already in the target group")
        self.member_repo.delete(member)
        created = self.member_repo.add(GroupMember(group_id=target_group_id, student_id=student_id))
        self.audit.record(organization_id=org_id, actor_user_id=actor_user_id, event_type=AuditEventType.STUDENT_UPDATED, entity_type="student", entity_id=student_id, metadata={"group_membership_changed": True})
        self.db.commit()
        return created
