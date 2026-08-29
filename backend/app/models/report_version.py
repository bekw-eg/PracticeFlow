import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class ReportVersion(UUIDPKMixin, TimestampMixin, Base):
    """Immutable snapshot created every time a student submits/resubmits (rule 23).
    Comments anchor to a specific report_version_id, so they remain valid history
    even after a newer version is created (rule 25)."""

    __tablename__ = "report_versions"
    __table_args__ = (UniqueConstraint("report_id", "version_number", name="uq_report_version_number"),)

    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reports.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # Structured document model, same shape as TemplateVersion.document_data,
    # merged with student content. Phase 1 stores the inherited `meta` + empty
    # content skeleton only — the block-level editor is Phase 2.
    document_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    report: Mapped["Report"] = relationship(back_populates="versions", foreign_keys=[report_id])
