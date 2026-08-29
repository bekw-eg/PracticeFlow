import uuid

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class Template(UUIDPKMixin, TimestampMixin, Base):
    """A reusable report template, e.g. 'Production Practice Report'.
    Holds no document content itself — content lives in immutable TemplateVersions."""

    __tablename__ = "templates"
    __table_args__ = (Index("ix_templates_org_name_id", "organization_id", "name", "id"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by_teacher_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teachers.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    organization: Mapped["Organization"] = relationship(back_populates="templates")
    versions: Mapped[list["TemplateVersion"]] = relationship(back_populates="template", order_by="TemplateVersion.version_number")
