"""Teacher-owned review folders and a review pinned to immutable analysis evidence."""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class ReviewGroup(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "review_groups"
    __table_args__ = (
        UniqueConstraint("organization_id", "teacher_id", "id", name="uq_review_groups_owner"),
        CheckConstraint("length(btrim(name)) BETWEEN 1 AND 255", name="ck_review_groups_name"),
        Index("ix_review_groups_owner_created", "organization_id", "teacher_id", "created_at", "id"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"))
    teacher_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("teachers.id", ondelete="RESTRICT"))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)


class TeacherDocumentReview(TimestampMixin, Base):
    __tablename__ = "teacher_document_reviews"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id", "submission_id"],
                             ["teacher_document_submissions.organization_id", "teacher_document_submissions.id"],
                             ondelete="RESTRICT", name="fk_teacher_review_submission"),
        ForeignKeyConstraint(["organization_id", "submission_id", "completed_job_id"],
                             ["document_check_jobs.organization_id", "document_check_jobs.teacher_submission_id", "document_check_jobs.id"],
                             ondelete="RESTRICT", name="fk_teacher_review_exact_job"),
        CheckConstraint("revision > 0", name="ck_teacher_review_revision"),
        CheckConstraint("length(remarks) <= 10000", name="ck_teacher_review_remarks"),
        CheckConstraint("(completed_at IS NULL AND completed_by_teacher_id IS NULL AND completed_job_id IS NULL) OR "
                        "(completed_at IS NOT NULL AND completed_by_teacher_id IS NOT NULL AND completed_job_id IS NOT NULL)",
                        name="ck_teacher_review_completion"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    submission_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    remarks: Mapped[str] = mapped_column(Text, default="")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_by_teacher_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("teachers.id", ondelete="RESTRICT"))
    completed_job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
