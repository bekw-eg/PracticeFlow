from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.organization import Organization


class OrganizationRepository:
    """Organizations themselves aren't tenant-scoped (there's nothing 'above'
    them to scope by) — this is the one repository that legitimately queries
    without an org_id filter."""

    def __init__(self, db: Session):
        self.db = db

    def get_by_slug(self, slug: str) -> Organization | None:
        stmt = select(Organization).where(Organization.slug == slug)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_id(self, org_id) -> Organization | None:
        return self.db.get(Organization, org_id)
