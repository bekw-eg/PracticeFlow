import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.membership import OrganizationMembership


class MembershipRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_user_and_org(self, user_id: uuid.UUID, org_id: uuid.UUID) -> OrganizationMembership | None:
        stmt = (
            select(OrganizationMembership)
            .options(joinedload(OrganizationMembership.role))
            .where(OrganizationMembership.user_id == user_id, OrganizationMembership.organization_id == org_id, OrganizationMembership.is_active.is_(True))
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list_by_user(self, user_id: uuid.UUID, offset: int = 0, limit: int | None = None) -> list[OrganizationMembership]:
        stmt = (
            select(OrganizationMembership)
            .options(joinedload(OrganizationMembership.role), joinedload(OrganizationMembership.organization))
            .where(OrganizationMembership.user_id == user_id, OrganizationMembership.is_active.is_(True))
            .order_by(OrganizationMembership.organization_id)
        )
        stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.db.execute(stmt).scalars().all())

    def count_by_user(self, user_id: uuid.UUID) -> int:
        stmt = select(func.count()).select_from(OrganizationMembership).where(
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.is_active.is_(True),
        )
        return int(self.db.scalar(stmt) or 0)

    def add(self, membership: OrganizationMembership) -> OrganizationMembership:
        self.db.add(membership)
        self.db.flush()
        return membership
