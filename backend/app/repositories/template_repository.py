import uuid

from sqlalchemy import select

from app.models.template import Template
from app.repositories.base import TenantScopedRepository


class TemplateRepository(TenantScopedRepository[Template]):
    model = Template

    def list_for_org(self, org_id: uuid.UUID, offset: int = 0, limit: int | None = None) -> list[Template]:
        stmt = select(Template).where(Template.organization_id == org_id).order_by(Template.name, Template.id).offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.db.execute(stmt).scalars().all())
