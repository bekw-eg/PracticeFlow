import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.template import Template
from app.models.template_version import TemplateVersion


class TemplateVersionRepository:
    """Scoped transitively through Template.organization_id."""

    def __init__(self, db: Session):
        self.db = db

    def get(self, org_id: uuid.UUID, version_id: uuid.UUID) -> TemplateVersion | None:
        stmt = (
            select(TemplateVersion)
            .join(Template, TemplateVersion.template_id == Template.id)
            .where(TemplateVersion.id == version_id, Template.organization_id == org_id)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list_for_template(self, org_id: uuid.UUID, template_id: uuid.UUID) -> list[TemplateVersion]:
        stmt = (
            select(TemplateVersion)
            .join(Template, TemplateVersion.template_id == Template.id)
            .where(TemplateVersion.template_id == template_id, Template.organization_id == org_id)
            .order_by(TemplateVersion.version_number)
        )
        return list(self.db.execute(stmt).scalars().all())

    def next_version_number(self, template_id: uuid.UUID) -> int:
        stmt = select(func.coalesce(func.max(TemplateVersion.version_number), 0)).where(
            TemplateVersion.template_id == template_id
        )
        current_max = self.db.execute(stmt).scalar_one()
        return current_max + 1

    def add(self, version: TemplateVersion) -> TemplateVersion:
        self.db.add(version)
        self.db.flush()
        return version
