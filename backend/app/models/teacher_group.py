import uuid

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class TeacherGroup(UUIDPKMixin, TimestampMixin, Base):
    """Which teacher(s) own/co-own which group. This is the join table that makes
    'My Groups' possible — a teacher's group list is exactly this table filtered by teacher_id."""

    __tablename__ = "teacher_groups"
    __table_args__ = (UniqueConstraint("teacher_id", "group_id", name="uq_teacher_group"),)

    teacher_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("teachers.id", ondelete="CASCADE"), nullable=False)
    group_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)

    teacher: Mapped["Teacher"] = relationship(back_populates="teacher_groups")
    group: Mapped["Group"] = relationship(back_populates="teacher_links")
