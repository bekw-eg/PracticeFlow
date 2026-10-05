"""add idempotency keys for durable notifications

Revision ID: c9d0e1f2a3b4
Revises: f6c3d4e5f6a7
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "c9d0e1f2a3b4"
down_revision: str | Sequence[str] | None = "f6c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable keeps existing event notifications backward compatible. In
    # PostgreSQL a unique constraint permits multiple NULL values.
    op.add_column("notifications", sa.Column("dedupe_key", sa.String(length=160), nullable=True))
    op.create_unique_constraint(
        "uq_notifications_org_user_dedupe_key",
        "notifications",
        ["organization_id", "user_id", "dedupe_key"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_notifications_org_user_dedupe_key", "notifications", type_="unique")
    op.drop_column("notifications", "dedupe_key")
