import uuid

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class Student(UUIDPKMixin, TimestampMixin, Base):
    """Role-specific profile for a STUDENT membership."""

    __tablename__ = "students"

    membership_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization_memberships.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    specialty_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("specialties.id", ondelete="SET NULL"), nullable=True
    )

    membership: Mapped["OrganizationMembership"] = relationship(back_populates="student_profile")
    specialty: Mapped["Specialty"] = relationship()
    group_memberships: Mapped[list["GroupMember"]] = relationship(back_populates="student")
    reports: Mapped[list["Report"]] = relationship(back_populates="student")
