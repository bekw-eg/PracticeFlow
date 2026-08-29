"""add optimistic-lock revisions to editable documents

Revision ID: a6b7c8d9e0f1
Revises: f5b2c3d4e5f6
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "a6b7c8d9e0f1"
down_revision: str | Sequence[str] | None = "f5b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing documents start at revision 1. The server default is removed
    # afterwards so application code remains the one explicit source of the
    # value for newly-created model instances.
    op.add_column("reports", sa.Column("revision", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("template_versions", sa.Column("revision", sa.Integer(), nullable=False, server_default="1"))
    op.alter_column("reports", "revision", server_default=None)
    op.alter_column("template_versions", "revision", server_default=None)


def downgrade() -> None:
    op.drop_column("template_versions", "revision")
    op.drop_column("reports", "revision")
