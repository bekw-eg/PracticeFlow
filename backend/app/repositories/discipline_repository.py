import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.dependencies.auth import RequestContext
from app.models.discipline import Discipline, DisciplineGroup, DisciplineTopic, TeachingMaterial
from app.models.group import Group
from app.models.teacher_group import TeacherGroup


class DisciplineRepository:
    """Every read is scoped by tenant AND the current owner."""
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def owned(ctx: RequestContext):
        return select(Discipline).where(
            Discipline.organization_id == ctx.organization_id,
            Discipline.created_by_user_id == ctx.user_id,
        )

    def get(self, ctx: RequestContext, discipline_id: uuid.UUID, *, lock: bool = False):
        query = self.owned(ctx).where(Discipline.id == discipline_id)
        return self.db.scalar(query.with_for_update() if lock else query)

    def page(self, query, offset: int, limit: int):
        total = int(self.db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0)
        return list(self.db.scalars(query.offset(offset).limit(limit))), total

    def disciplines(self, ctx, archived: bool, offset: int, limit: int):
        return self.page(self.owned(ctx).where(Discipline.is_archived == archived)
                         .order_by(Discipline.created_at.desc(), Discipline.id.desc()), offset, limit)

    def topic(self, ctx, topic_id: uuid.UUID):
        return self.db.scalar(select(DisciplineTopic).join(
            Discipline, (Discipline.id == DisciplineTopic.discipline_id)
            & (Discipline.organization_id == DisciplineTopic.organization_id),
        ).where(DisciplineTopic.id == topic_id, Discipline.organization_id == ctx.organization_id,
                Discipline.created_by_user_id == ctx.user_id))

    def topics(self, ctx, discipline_id, archived: bool, offset: int, limit: int):
        query = select(DisciplineTopic).join(Discipline,
            (Discipline.id == DisciplineTopic.discipline_id) & (Discipline.organization_id == DisciplineTopic.organization_id)
        ).where(
            DisciplineTopic.organization_id == ctx.organization_id, DisciplineTopic.discipline_id == discipline_id,
            Discipline.created_by_user_id == ctx.user_id,
            DisciplineTopic.is_archived == archived,
        ).order_by(DisciplineTopic.position, DisciplineTopic.id)
        return self.page(query, offset, limit)

    def next_position(self, organization_id, discipline_id):
        value = self.db.scalar(select(func.max(DisciplineTopic.position)).where(
            DisciplineTopic.organization_id == organization_id, DisciplineTopic.discipline_id == discipline_id,
        ))
        return 0 if value is None else value + 1

    def groups(self, ctx, discipline_id):
        return list(self.db.scalars(select(Group).join(DisciplineGroup,
            (DisciplineGroup.group_id == Group.id) & (DisciplineGroup.organization_id == Group.organization_id)
        ).join(TeacherGroup, TeacherGroup.group_id == Group.id).where(
            DisciplineGroup.organization_id == ctx.organization_id, DisciplineGroup.discipline_id == discipline_id,
            TeacherGroup.teacher_id == ctx.teacher_id,
            DisciplineGroup.discipline_id.in_(self.owned(ctx).with_only_columns(Discipline.id)),
        ).order_by(Group.name, Group.id)))

    def replace_groups(self, ctx, discipline_id, group_ids):
        self.db.execute(delete(DisciplineGroup).where(
            DisciplineGroup.organization_id == ctx.organization_id, DisciplineGroup.discipline_id == discipline_id,
        ))
        self.db.add_all([DisciplineGroup(organization_id=ctx.organization_id, discipline_id=discipline_id, group_id=value)
                         for value in set(group_ids)])

    def material(self, ctx, material_id, *, include_deleted: bool = False):
        query = select(TeachingMaterial).join(Discipline,
            (Discipline.id == TeachingMaterial.discipline_id) & (Discipline.organization_id == TeachingMaterial.organization_id)
        ).where(TeachingMaterial.id == material_id, TeachingMaterial.organization_id == ctx.organization_id,
                TeachingMaterial.uploaded_by_user_id == ctx.user_id, Discipline.created_by_user_id == ctx.user_id)
        if not include_deleted:
            query = query.where(TeachingMaterial.deleted_at.is_(None))
        return self.db.scalar(query)

    def materials(self, ctx, topic_id, offset: int, limit: int):
        return self.page(select(TeachingMaterial).where(
            TeachingMaterial.organization_id == ctx.organization_id, TeachingMaterial.uploaded_by_user_id == ctx.user_id,
            TeachingMaterial.topic_id == topic_id, TeachingMaterial.deleted_at.is_(None),
        ).order_by(TeachingMaterial.created_at.desc(), TeachingMaterial.id.desc()), offset, limit)

    def previous_upload(self, ctx, topic_id, key):
        return self.db.scalar(select(TeachingMaterial).where(
            TeachingMaterial.organization_id == ctx.organization_id, TeachingMaterial.topic_id == topic_id,
            TeachingMaterial.uploaded_by_user_id == ctx.user_id, TeachingMaterial.idempotency_key == key,
        ))
