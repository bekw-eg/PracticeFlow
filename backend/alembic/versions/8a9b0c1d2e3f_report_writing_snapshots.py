"""Counts-only writing history for student report drafts."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "8a9b0c1d2e3f"
down_revision = "7f8091a2b3c4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "report_writing_snapshots",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("report_id", pg.UUID(as_uuid=True), sa.ForeignKey("reports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("word_count", sa.Integer(), nullable=False),
        sa.Column("words_added", sa.Integer(), nullable=False),
        sa.Column("largest_save_words", sa.Integer(), nullable=False),
        sa.Column("save_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("word_count >= 0", name="ck_report_writing_snapshots_word_count"),
        sa.CheckConstraint("largest_save_words >= 0", name="ck_report_writing_snapshots_largest_save"),
        sa.CheckConstraint("save_count >= 1", name="ck_report_writing_snapshots_save_count"),
    )
    op.create_index("ix_report_writing_snapshots_organization_id", "report_writing_snapshots", ["organization_id"])
    op.create_index("ix_report_writing_snapshots_report_created", "report_writing_snapshots", ["report_id", "created_at"])


def downgrade():
    op.drop_index("ix_report_writing_snapshots_report_created", table_name="report_writing_snapshots")
    op.drop_index("ix_report_writing_snapshots_organization_id", table_name="report_writing_snapshots")
    op.drop_table("report_writing_snapshots")
