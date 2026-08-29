"""add durable asynchronous export jobs

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "d9e0f1a2b3c4"
down_revision: str | Sequence[str] | None = "c8d9e0f1a2b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "export_jobs",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("report_id", sa.UUID(), nullable=False),
        sa.Column("requested_by_user_id", sa.UUID(), nullable=False),
        sa.Column("requested_role", sa.String(length=20), nullable=False),
        sa.Column("format", sa.String(length=8), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="queued"),
        sa.Column("dedupe_key", sa.String(length=80), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=True),
        sa.Column("content_type", sa.String(length=120), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("worker_id", sa.String(length=100), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("format IN ('docx', 'pdf')", name="ck_export_jobs_format"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'timed_out', 'cancelled')",
            name="ck_export_jobs_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["report_id"], ["reports.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_export_jobs_org_created_id", "export_jobs", ["organization_id", "created_at", "id"])
    op.create_index("ix_export_jobs_status_lease", "export_jobs", ["status", "lease_expires_at"])
    op.create_index("ix_export_jobs_expires_at", "export_jobs", ["expires_at"])
    # This is the atomic deduplication guard for API replicas. Completed jobs
    # do not participate, so a later explicit export remains possible.
    op.execute(
        "CREATE UNIQUE INDEX uq_export_jobs_active_dedupe "
        "ON export_jobs (organization_id, dedupe_key) "
        "WHERE status IN ('queued', 'running')"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_export_jobs_active_dedupe")
    op.drop_index("ix_export_jobs_expires_at", table_name="export_jobs")
    op.drop_index("ix_export_jobs_status_lease", table_name="export_jobs")
    op.drop_index("ix_export_jobs_org_created_id", table_name="export_jobs")
    op.drop_table("export_jobs")
