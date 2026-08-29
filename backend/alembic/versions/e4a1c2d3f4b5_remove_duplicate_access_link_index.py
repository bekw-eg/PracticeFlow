"""remove duplicate access link token index

Revision ID: e4a1c2d3f4b5
Revises: d21f3b4e5c6d
"""
from typing import Sequence, Union

from alembic import op


revision: str = "e4a1c2d3f4b5"
down_revision: Union[str, Sequence[str], None] = "d21f3b4e5c6d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # d21f3b4e5c6d created both a UNIQUE constraint and an equivalent UNIQUE
    # index for token_hash. PostgreSQL already backs the constraint with its
    # own index, so retain the constraint and remove only the duplicate.
    op.drop_index("ix_access_links_token_hash", table_name="access_links")


def downgrade() -> None:
    op.create_index("ix_access_links_token_hash", "access_links", ["token_hash"], unique=True)
