"""Separate retention controls from immutable teacher submissions."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "3b4c5d6e7f80"
down_revision = "2a3b4c5d6e7f"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TYPE audit_event_type ADD VALUE IF NOT EXISTS 'TEACHER_DOCUMENT_CHECK_MANAGED'")
    op.create_table(
        "teacher_document_lifecycle",
        sa.Column("organization_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("submission_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.Column("disclosure_allowed", sa.Boolean(), nullable=False),
        sa.Column("original_delete_requested_at", sa.DateTime(timezone=True)),
        sa.Column("original_deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id", "submission_id"],
                                ["teacher_document_submissions.organization_id", "teacher_document_submissions.id"],
                                ondelete="RESTRICT", name="fk_teacher_lifecycle_submission"),
        sa.CheckConstraint("revision > 0", name="ck_teacher_lifecycle_revision"),
        sa.CheckConstraint("original_deleted_at IS NULL OR original_delete_requested_at IS NOT NULL",
                           name="ck_teacher_lifecycle_deletion"),
    )


def downgrade():
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM teacher_document_lifecycle) THEN
        RAISE EXCEPTION 'Cannot discard document retention decisions; roll forward';
      END IF;
    END $$;""")
    op.drop_table("teacher_document_lifecycle")
