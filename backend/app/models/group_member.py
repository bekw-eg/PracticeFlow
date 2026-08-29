import uuid

from sqlalchemy import ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class GroupMember(UUIDPKMixin, TimestampMixin, Base):
    """A student's membership in a group. A student typically belongs to one active group,
    but this is modeled many-to-many to support transfers/history without data loss."""

    __tablename__ = "group_members"
    __table_args__ = (
        UniqueConstraint("group_id", "student_id", name="uq_group_member"),
        Index("ix_group_members_group_id_id", "group_id", "id"),
    )

    group_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    student_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False)

    group: Mapped["Group"] = relationship(back_populates="members")
    student: Mapped["Student"] = relationship(back_populates="group_memberships")
