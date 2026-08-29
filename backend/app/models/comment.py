import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import CommentStatus


class Comment(UUIDPKMixin, TimestampMixin, Base):
    """A teacher review comment, anchored to a specific ReportVersion's
    document content (rule 6/7/12) — never to screen coordinates, a DOM
    path, or an array index.

    Two shapes share this table:
    - Inline comment: node_id/start_offset/end_offset/text_snapshot set,
      anchored to one text range inside a specific block.
    - General comment: is_general=True, all anchor fields null — a
      report-level note not tied to any text (rule 19).

    Replies (rule 9) are rows with parent_comment_id set, forming a flat
    thread under the root comment — deliberately not a tree, matching the
    spec's "document-review oriented, not Slack-like" instruction.

    anchor validity is NOT stored here — it's computed at read time against
    the CURRENT document content (see app/services/comment_service.py),
    so it always reflects the live state rather than going stale.
    """

    __tablename__ = "comments"
    __table_args__ = (
        Index("ix_comments_org_report_parent_created_id", "organization_id", "report_id", "parent_comment_id", "created_at", "id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    report_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("reports.id", ondelete="CASCADE"), nullable=False, index=True)
    report_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    parent_comment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("comments.id", ondelete="CASCADE"), nullable=True, index=True
    )

    is_general: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    node_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_offset: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_offset: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)

    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[CommentStatus] = mapped_column(Enum(CommentStatus, name="comment_status"), default=CommentStatus.OPEN, nullable=False)

    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    author: Mapped["User"] = relationship(foreign_keys=[author_user_id])
    replies: Mapped[list["Comment"]] = relationship(
        back_populates="parent", cascade="all, delete-orphan", order_by="Comment.created_at"
    )
    parent: Mapped["Comment | None"] = relationship(back_populates="replies", remote_side="Comment.id")
