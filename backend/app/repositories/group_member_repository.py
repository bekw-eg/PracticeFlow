import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.group import Group
from app.models.group_member import GroupMember
from app.models.membership import OrganizationMembership
from app.models.student import Student


class GroupMemberRepository:
    """Scoped transitively through Group.organization_id — GroupMember has no
    direct organization_id column."""

    def __init__(self, db: Session):
        self.db = db

    def list_for_group(self, org_id: uuid.UUID, group_id: uuid.UUID, offset: int = 0, limit: int | None = None) -> list[GroupMember]:
        stmt = (
            select(GroupMember)
            .join(Group, GroupMember.group_id == Group.id)
            .options(joinedload(GroupMember.student).joinedload(Student.membership).joinedload(OrganizationMembership.user))
            .where(GroupMember.group_id == group_id, Group.organization_id == org_id)
            .order_by(GroupMember.id)
        )
        stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.db.execute(stmt).unique().scalars().all())

    def count_for_group(self, org_id: uuid.UUID, group_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(GroupMember)
            .join(Group, GroupMember.group_id == Group.id)
            .where(GroupMember.group_id == group_id, Group.organization_id == org_id)
        )
        return int(self.db.scalar(stmt) or 0)

    def exists(self, group_id: uuid.UUID, student_id: uuid.UUID) -> bool:
        stmt = select(GroupMember).where(GroupMember.group_id == group_id, GroupMember.student_id == student_id)
        return self.db.execute(stmt).scalar_one_or_none() is not None

    def add(self, member: GroupMember) -> GroupMember:
        self.db.add(member)
        self.db.flush()
        return member

    def get(self, org_id: uuid.UUID, group_id: uuid.UUID, student_id: uuid.UUID) -> GroupMember | None:
        stmt = select(GroupMember).join(Group).where(Group.organization_id == org_id, GroupMember.group_id == group_id, GroupMember.student_id == student_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def delete(self, member: GroupMember) -> None:
        self.db.delete(member)
        self.db.flush()
