"""add audit event values introduced after the initial schema

Revision ID: f5b2c3d4e5f6
Revises: e4a1c2d3f4b5
"""
from collections.abc import Sequence

from alembic import op


revision: str = "f5b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "e4a1c2d3f4b5"
branch_labels = None
depends_on = None

_VALUES = (
    "REPORT_RESUBMITTED",
    "REVIEW_STARTED",
    "COMMENT_REPLIED",
    "REPORT_LOCKED",
    "DOCX_GENERATED",
    "PDF_GENERATED",
)


def upgrade() -> None:
    for value in _VALUES:
        op.execute(f"ALTER TYPE audit_event_type ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    # PostgreSQL cannot remove an enum value without rebuilding the type and
    # every dependent column. Keeping now-valid audit history is safer than a
    # destructive downgrade that could discard production events.
    pass
