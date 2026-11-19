import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class ReportWritingSnapshot(UUIDPKMixin, TimestampMixin, Base):
    """How a student's working draft grew over time — counts only, never text.

    Saves that land within a short window of each other are folded into one
    row (``created_at`` is when the window opened, ``updated_at`` the last
    save in it), so autosave does not create a row per keystroke.
    ``largest_save_words`` keeps the biggest single-save increase in the
    window, which is what distinguishes a large paste from steady typing.
    """

    __tablename__ = "report_writing_snapshots"
    __table_args__ = (
        Index("ix_report_writing_snapshots_report_created", "report_id", "created_at"),
        CheckConstraint("word_count >= 0", name="ck_report_writing_snapshots_word_count"),
        CheckConstraint("largest_save_words >= 0", name="ck_report_writing_snapshots_largest_save"),
        CheckConstraint("save_count >= 1", name="ck_report_writing_snapshots_save_count"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reports.id", ondelete="CASCADE"), nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False)
    words_added: Mapped[int] = mapped_column(Integer, nullable=False)
    largest_save_words: Mapped[int] = mapped_column(Integer, nullable=False)
    save_count: Mapped[int] = mapped_column(Integer, nullable=False)
