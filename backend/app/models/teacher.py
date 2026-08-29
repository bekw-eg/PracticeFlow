import uuid

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class Teacher(UUIDPKMixin, TimestampMixin, Base):
    """Role-specific profile for a TEACHER membership."""

    __tablename__ = "teachers"

    membership_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization_memberships.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True
    )

    membership: Mapped["OrganizationMembership"] = relationship(back_populates="teacher_profile")
    department: Mapped["Department"] = relationship()
    teacher_groups: Mapped[list["TeacherGroup"]] = relationship(back_populates="teacher")
