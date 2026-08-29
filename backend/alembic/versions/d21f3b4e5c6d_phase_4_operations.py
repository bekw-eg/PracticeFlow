"""phase 4: membership lifecycle, notifications and access links

Revision ID: d21f3b4e5c6d
Revises: c66ecf64c66f
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d21f3b4e5c6d"
down_revision: Union[str, Sequence[str], None] = "c66ecf64c66f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organization_memberships", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.alter_column("organization_memberships", "is_active", server_default=None)
    op.add_column("refresh_tokens", sa.Column("organization_id", sa.UUID(), nullable=True))
    op.create_foreign_key("fk_refresh_tokens_organization_id", "refresh_tokens", "organizations", ["organization_id"], ["id"], ondelete="CASCADE")
    op.create_index(op.f("ix_refresh_tokens_organization_id"), "refresh_tokens", ["organization_id"])
    op.create_table(
        "access_links",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(op.f("ix_access_links_organization_id"), "access_links", ["organization_id"])
    op.create_index(op.f("ix_access_links_user_id"), "access_links", ["user_id"])
    op.create_index(op.f("ix_access_links_token_hash"), "access_links", ["token_hash"], unique=True)
    op.create_table(
        "notifications",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("type", sa.String(length=60), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("link", sa.String(length=500), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_notifications_organization_id"), "notifications", ["organization_id"])
    op.create_index(op.f("ix_notifications_user_id"), "notifications", ["user_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_notifications_user_id"), table_name="notifications")
    op.drop_index(op.f("ix_notifications_organization_id"), table_name="notifications")
    op.drop_table("notifications")
    op.drop_index(op.f("ix_access_links_token_hash"), table_name="access_links")
    op.drop_index(op.f("ix_access_links_user_id"), table_name="access_links")
    op.drop_index(op.f("ix_access_links_organization_id"), table_name="access_links")
    op.drop_table("access_links")
    op.drop_column("organization_memberships", "is_active")
    op.drop_index(op.f("ix_refresh_tokens_organization_id"), table_name="refresh_tokens")
    op.drop_constraint("fk_refresh_tokens_organization_id", "refresh_tokens", type_="foreignkey")
    op.drop_column("refresh_tokens", "organization_id")
