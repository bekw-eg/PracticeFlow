from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class Role(UUIDPKMixin, TimestampMixin, Base):
    """Global role catalog (SUPER_ADMIN / DIRECTOR / TEACHER / STUDENT).

    Kept as a table rather than a bare enum so future org-specific roles /
    permission sets can be introduced without a breaking schema change.
    """

    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    memberships: Mapped[list["OrganizationMembership"]] = relationship(back_populates="role")
