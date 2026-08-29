import uuid

from sqlalchemy import ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class TemplateVersion(UUIDPKMixin, TimestampMixin, Base):
    """A snapshot of a template's document structure.

    Mutable while UNLOCKED — i.e. while no Internship references it yet, so
    the teacher's editor can save iteratively. Becomes LOCKED (immutable)
    the moment any Internship is created against it (rule 5/30): editing a
    locked version is rejected at the service layer; the teacher must create
    a new version instead. `TemplateVersionService.is_locked()` is the single
    source of truth for this check — see app/services/template_service.py.
    """

    __tablename__ = "template_versions"
    __table_args__ = (UniqueConstraint("template_id", "version_number", name="uq_template_version_number"),)

    template_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("templates.id", ondelete="CASCADE"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # Structured document model (see app/documents). Phase 1 populates only `meta`
    # (page size, margins, fonts, spacing) — block-level content editing is Phase 2.
    document_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Bumped by every successful document PATCH and used for optimistic
    # locking between multiple teacher editor tabs.
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    is_published: Mapped[bool] = mapped_column(default=True, nullable=False)

    template: Mapped["Template"] = relationship(back_populates="versions")
    internships: Mapped[list["Internship"]] = relationship(back_populates="template_version")
