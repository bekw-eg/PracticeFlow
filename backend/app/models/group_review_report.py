"""Private group presentation drafts with immutable evidence snapshots."""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKeyConstraint, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class GroupReviewReport(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "group_review_reports"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id", "teacher_id", "group_id"],
                             ["review_groups.organization_id", "review_groups.teacher_id", "review_groups.id"],
                             ondelete="RESTRICT", name="fk_group_review_report_owner"),
        UniqueConstraint("organization_id", "teacher_id", "group_id", "request_id", name="uq_group_report_request"),
        CheckConstraint("revision > 0", name="ck_group_report_revision"),
        CheckConstraint("locale IN ('ru', 'kk', 'en')", name="ck_group_report_locale"),
        CheckConstraint("jsonb_typeof(snapshot) = 'object' AND jsonb_typeof(content) = 'object'", name="ck_group_report_json"),
        CheckConstraint("(storage_key IS NULL AND generated_at IS NULL) OR "
                        "(storage_key IS NOT NULL AND generated_at IS NOT NULL)", name="ck_group_report_generated"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    teacher_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    group_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    locale: Mapped[str] = mapped_column(String(2), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(512))
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
