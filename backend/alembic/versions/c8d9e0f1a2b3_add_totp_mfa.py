"""add TOTP MFA credentials, recovery codes and short-lived challenges

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "c8d9e0f1a2b3"
down_revision: str | Sequence[str] | None = "b7c8d9e0f1a2"
branch_labels = None
depends_on = None

_AUDIT_VALUES = (
    "MFA_CHALLENGE_CREATED", "MFA_ENROLLED", "MFA_VERIFIED", "MFA_RECOVERY_USED",
    "MFA_RECOVERY_REQUESTED", "MFA_RECOVERY_APPROVED", "MFA_RESET", "MFA_BREAK_GLASS_STARTED",
)


def upgrade() -> None:
    for value in _AUDIT_VALUES:
        op.execute(f"ALTER TYPE audit_event_type ADD VALUE IF NOT EXISTS '{value}'")

    op.create_table(
        "mfa_credentials",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("secret_encrypted", sa.Text(), nullable=False),
        sa.Column("enabled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("security_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_totp_counter", sa.Integer(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mfa_credentials_user_id", "mfa_credentials", ["user_id"], unique=True)
    op.create_table(
        "mfa_recovery_codes",
        sa.Column("credential_id", sa.UUID(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["credential_id"], ["mfa_credentials.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("credential_id", "code_hash", name="uq_mfa_recovery_code"),
    )
    op.create_index("ix_mfa_recovery_codes_credential_id", "mfa_recovery_codes", ["credential_id"])
    op.create_table(
        "mfa_challenges",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("membership_id", sa.UUID(), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("cookie_hash", sa.String(length=64), nullable=False),
        sa.Column("pending_secret_encrypted", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by_user_id", sa.UUID(), nullable=True),
        sa.Column("recovery_code_hash", sa.String(length=64), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["membership_id"], ["organization_memberships.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mfa_challenges_user_id", "mfa_challenges", ["user_id"])
    op.create_index("ix_mfa_challenges_organization_id", "mfa_challenges", ["organization_id"])
    op.create_index("ix_mfa_challenges_expires_at", "mfa_challenges", ["expires_at"])
    op.add_column("refresh_tokens", sa.Column("mfa_verified", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("refresh_tokens", sa.Column("mfa_security_version", sa.Integer(), nullable=True))
    op.alter_column("refresh_tokens", "mfa_verified", server_default=None)


def downgrade() -> None:
    op.drop_column("refresh_tokens", "mfa_security_version")
    op.drop_column("refresh_tokens", "mfa_verified")
    op.drop_index("ix_mfa_challenges_expires_at", table_name="mfa_challenges")
    op.drop_index("ix_mfa_challenges_organization_id", table_name="mfa_challenges")
    op.drop_index("ix_mfa_challenges_user_id", table_name="mfa_challenges")
    op.drop_table("mfa_challenges")
    op.drop_index("ix_mfa_recovery_codes_credential_id", table_name="mfa_recovery_codes")
    op.drop_table("mfa_recovery_codes")
    op.drop_index("ix_mfa_credentials_user_id", table_name="mfa_credentials")
    op.drop_table("mfa_credentials")
    # Audit enum values are intentionally retained, preserving historical data.
