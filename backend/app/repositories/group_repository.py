import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.group import Group
from app.models.teacher_group import TeacherGroup
from app.repositories.base import TenantScopedRepository


class GroupRepository(TenantScopedRepository[Group]):
    model = Group

    def list_for_teacher(self, org_id: uuid.UUID, teacher_id: uuid.UUID, offset: int = 0, limit: int | None = None) -> list[Group]:
        """This is the query behind 'My Groups' — a teacher only ever sees
        groups they're explicitly linked to via teacher_groups, never every
        group in the org."""
        stmt = (
            select(Group)
            .join(TeacherGroup, TeacherGroup.group_id == Group.id)
            .where(TeacherGroup.teacher_id == teacher_id, Group.organization_id == org_id)
            .order_by(Group.name, Group.id)
        )
        stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.db.execute(stmt).scalars().all())

    def count_for_teacher(self, org_id: uuid.UUID, teacher_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(Group)
            .join(TeacherGroup, TeacherGroup.group_id == Group.id)
            .where(TeacherGroup.teacher_id == teacher_id, Group.organization_id == org_id)
        )
        return int(self.db.scalar(stmt) or 0)

    def teacher_owns_group(self, db: Session, teacher_id: uuid.UUID, group_id: uuid.UUID) -> bool:
        stmt = select(TeacherGroup).where(TeacherGroup.teacher_id == teacher_id, TeacherGroup.group_id == group_id)
        return db.execute(stmt).scalar_one_or_none() is not None
