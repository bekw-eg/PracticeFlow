"""add tenant audit hash chains and investigation indexes

Revision ID: f6c3d4e5f6a7
Revises: d9e0f1a2b3c4
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f6c3d4e5f6a7"
down_revision: str | Sequence[str] | None = "d9e0f1a2b3c4"
branch_labels = None
depends_on = None

_VALUES = (
    "MEMBERSHIP_CREATED", "MEMBERSHIP_ROLE_CHANGED", "MEMBERSHIP_ACTIVATED", "MEMBERSHIP_DEACTIVATED",
    "MEMBERSHIP_DELETED", "INVITE_CREATED", "PASSWORD_RESET_CREATED", "PASSWORD_RESET_COMPLETED",
    "ORGANIZATION_CREATED", "ORGANIZATION_UPDATED", "GROUP_CREATED", "GROUP_TEACHERS_UPDATED",
    "DEPARTMENT_CREATED", "SPECIALTY_CREATED", "TEACHER_UPDATED", "STUDENT_UPDATED",
    "FILE_DOWNLOADED", "FILE_DELETED", "EXPORT_REQUESTED", "EXPORT_DOWNLOADED", "EXPORT_FILE_DELETED",
    "AUDIT_LOG_VIEWED", "AUDIT_INTEGRITY_VERIFIED", "AUDIT_RETENTION_CHECKPOINT",
)


def upgrade() -> None:
    for value in _VALUES:
        op.execute(f"ALTER TYPE audit_event_type ADD VALUE IF NOT EXISTS '{value}'")

    op.add_column("audit_logs", sa.Column("sequence", sa.Integer(), nullable=True))
    op.add_column("audit_logs", sa.Column("previous_hash", sa.String(length=64), nullable=True))
    op.add_column("audit_logs", sa.Column("event_hash", sa.String(length=64), nullable=True))
    op.add_column("audit_logs", sa.Column("request_id_hash", sa.String(length=64), nullable=True))
    op.add_column("audit_logs", sa.Column("correlation_id_hash", sa.String(length=64), nullable=True))
    op.add_column("audit_logs", sa.Column("source_ip_hash", sa.String(length=64), nullable=True))
    op.create_index("ix_audit_logs_org_sequence", "audit_logs", ["organization_id", "sequence"], unique=True)
    op.create_index("ix_audit_logs_org_action_created_id", "audit_logs", ["organization_id", "event_type", "created_at", "id"])
    op.create_index("ix_audit_logs_org_actor_created_id", "audit_logs", ["organization_id", "actor_user_id", "created_at", "id"])
    op.create_table(
        "audit_chain_heads",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("last_sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_hash", sa.String(length=64), nullable=False),
        sa.Column("retention_anchor_sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retention_anchor_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("organization_id"),
    )


def downgrade() -> None:
    op.drop_table("audit_chain_heads")
    op.drop_index("ix_audit_logs_org_actor_created_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_org_action_created_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_org_sequence", table_name="audit_logs")
    op.drop_column("audit_logs", "source_ip_hash")
    op.drop_column("audit_logs", "correlation_id_hash")
    op.drop_column("audit_logs", "request_id_hash")
    op.drop_column("audit_logs", "event_hash")
    op.drop_column("audit_logs", "previous_hash")
    op.drop_column("audit_logs", "sequence")
    # PostgreSQL enum values are intentionally retained to preserve history.
