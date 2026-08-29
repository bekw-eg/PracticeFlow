import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import ExportFormat, ExportJobStatus


class ExportJob(UUIDPKMixin, TimestampMixin, Base):
    """Durable export ledger. The queue is only a delivery mechanism.

    ``dedupe_key`` is a report+format identity. PostgreSQL's partial unique
    index (created in the migration) permits exactly one queued/running job
    for it, even when two API replicas receive a retry simultaneously.
    """

    __tablename__ = "export_jobs"
    __table_args__ = (
        CheckConstraint("format IN ('docx', 'pdf')", name="ck_export_jobs_format"),
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'timed_out', 'cancelled')",
            name="ck_export_jobs_status",
        ),
        Index("ix_export_jobs_org_created_id", "organization_id", "created_at", "id"),
        Index("ix_export_jobs_status_lease", "status", "lease_expires_at"),
        Index("ix_export_jobs_expires_at", "expires_at"),
        Index(
            "uq_export_jobs_active_dedupe",
            "organization_id",
            "dedupe_key",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reports.id", ondelete="CASCADE"), nullable=False
    )
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    requested_role: Mapped[str] = mapped_column(String(20), nullable=False)
    format: Mapped[ExportFormat] = mapped_column(String(8), nullable=False)
    status: Mapped[ExportJobStatus] = mapped_column(String(16), nullable=False, default=ExportJobStatus.QUEUED)
    dedupe_key: Mapped[str] = mapped_column(String(80), nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
