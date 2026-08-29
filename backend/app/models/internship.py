import uuid
from datetime import date

from sqlalchemy import Date, Enum, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import InternshipStatus


class Internship(UUIDPKMixin, TimestampMixin, Base):
    """Created inside a group. Its template_version_id is FIXED at creation time —
    later template versions never retroactively affect an existing internship (rule 9)."""

    __tablename__ = "internships"
    __table_args__ = (Index("ix_internships_org_group_created_id", "organization_id", "group_id", "created_at", "id"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    group_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True)
    template_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("template_versions.id", ondelete="RESTRICT"), nullable=False
    )
    created_by_teacher_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teachers.id", ondelete="RESTRICT"), nullable=False
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    specialty_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("specialties.id", ondelete="SET NULL"), nullable=True
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    deadline: Mapped[date] = mapped_column(Date, nullable=False)

    status: Mapped[InternshipStatus] = mapped_column(
        Enum(InternshipStatus, name="internship_status"), default=InternshipStatus.DRAFT, nullable=False
    )

    group: Mapped["Group"] = relationship(back_populates="internships")
    template_version: Mapped["TemplateVersion"] = relationship(back_populates="internships")
    reports: Mapped[list["Report"]] = relationship(back_populates="internship")
