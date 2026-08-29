import uuid

from sqlalchemy import exists, func, select

from app.models.internship import Internship
from app.repositories.base import TenantScopedRepository


class InternshipRepository(TenantScopedRepository[Internship]):
    model = Internship

    def list_for_group(self, org_id: uuid.UUID, group_id: uuid.UUID, offset: int = 0, limit: int | None = None) -> list[Internship]:
        stmt = (
            select(Internship)
            .where(Internship.organization_id == org_id, Internship.group_id == group_id)
            .order_by(Internship.created_at.desc(), Internship.id.desc())
        )
        stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.db.execute(stmt).scalars().all())

    def count_for_group(self, org_id: uuid.UUID, group_id: uuid.UUID) -> int:
        stmt = select(func.count()).select_from(Internship).where(
            Internship.organization_id == org_id, Internship.group_id == group_id
        )
        return int(self.db.scalar(stmt) or 0)

    def any_uses_template_version(self, template_version_id: uuid.UUID) -> bool:
        """Whether ANY internship (in any organization — a template version's
        id is already tenant-unambiguous once resolved) references this
        version. Used to decide if a TemplateVersion is still editable."""
        stmt = select(exists().where(Internship.template_version_id == template_version_id))
        return bool(self.db.execute(stmt).scalar())
