from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import RoleName
from app.models.role import Role


class RoleRepository:
    """Global role catalog — not tenant-scoped."""

    def __init__(self, db: Session):
        self.db = db

    def get_by_name(self, name: RoleName) -> Role | None:
        stmt = select(Role).where(Role.name == name.value)
        return self.db.execute(stmt).scalar_one_or_none()
