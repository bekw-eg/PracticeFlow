import uuid
from typing import Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class TenantScopedRepository(Generic[ModelT]):
    """Base repository for any table that has an `organization_id` column.

    Every read/write method requires an explicit org_id and applies it as a
    mandatory filter. There is no method on this class that can query the
    table without a tenant filter — that's a structural guarantee, not a
    convention someone has to remember per-endpoint.

    Subclasses for tables WITHOUT a direct organization_id (e.g. group_members,
    which is scoped transitively through its group) must derive their own
    tenant-safe queries rather than using this base directly.
    """

    model: type[ModelT]

    def __init__(self, db: Session):
        self.db = db

    def get(self, org_id: uuid.UUID, obj_id: uuid.UUID) -> ModelT | None:
        stmt = select(self.model).where(self.model.id == obj_id, self.model.organization_id == org_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def list(self, org_id: uuid.UUID, *, offset: int = 0, limit: int | None = None, **filters) -> list[ModelT]:
        stmt = select(self.model).where(self.model.organization_id == org_id)
        for key, value in filters.items():
            stmt = stmt.where(getattr(self.model, key) == value)
        stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.db.execute(stmt).scalars().all())

    def count(self, org_id: uuid.UUID, **filters) -> int:
        """Count with the same mandatory tenant predicate as ``list``."""
        stmt = select(func.count()).select_from(self.model).where(self.model.organization_id == org_id)
        for key, value in filters.items():
            stmt = stmt.where(getattr(self.model, key) == value)
        return int(self.db.scalar(stmt) or 0)

    def add(self, obj: ModelT) -> ModelT:
        self.db.add(obj)
        self.db.flush()
        return obj

    def delete(self, obj: ModelT) -> None:
        self.db.delete(obj)
        self.db.flush()
