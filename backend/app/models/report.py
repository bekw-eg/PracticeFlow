import uuid

from sqlalchemy import Enum, ForeignKey, Index, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import ReportStatus


class Report(UUIDPKMixin, TimestampMixin, Base):
    """One per (internship, student).

    Phase 2 adds `document_data`: the student's CURRENT WORKING DRAFT, editable
    while status is DRAFT/REVISION_REQUIRED. This is intentionally separate
    from ReportVersion — versions are immutable snapshots taken at submit
    time (rule 23); the working draft is the one thing in this whole schema
    that's allowed to be mutated in place, because it hasn't been submitted
    yet and therefore isn't part of the historical record."""

    __tablename__ = "reports"
    __table_args__ = (
        UniqueConstraint("internship_id", "student_id", name="uq_report_internship_student"),
        Index("ix_reports_org_student_created_id", "organization_id", "student_id", "created_at", "id"),
        Index("ix_reports_org_internship_created_id", "organization_id", "internship_id", "created_at", "id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    internship_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("internships.id", ondelete="CASCADE"), nullable=False, index=True
    )
    student_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False)

    status: Mapped[ReportStatus] = mapped_column(Enum(ReportStatus, name="report_status"), default=ReportStatus.DRAFT, nullable=False)

    # Working draft — initialized from the internship's fixed TemplateVersion
    # when the report is created (internship publish), edited in place by the
    # student, frozen into an immutable ReportVersion on submit.
    document_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    document_schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Compare-and-swap token for the editable working draft. It is distinct
    # from ReportVersion.version_number, which tracks immutable submissions.
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Points at the version currently "in play" (latest submitted, or the draft being edited).
    # Historical versions remain reachable through `versions`, never deleted or overwritten.
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("report_versions.id", ondelete="SET NULL", use_alter=True, name="fk_reports_current_version_id"),
        nullable=True,
    )

    internship: Mapped["Internship"] = relationship(back_populates="reports")
    student: Mapped["Student"] = relationship(back_populates="reports")
    versions: Mapped[list["ReportVersion"]] = relationship(
        back_populates="report", order_by="ReportVersion.version_number", foreign_keys="ReportVersion.report_id"
    )
