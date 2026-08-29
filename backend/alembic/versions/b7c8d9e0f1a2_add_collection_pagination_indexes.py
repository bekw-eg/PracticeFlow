"""add indexes for paginated collection queries

Revision ID: b7c8d9e0f1a2
Revises: a6b7c8d9e0f1
"""
from collections.abc import Sequence

from alembic import op


revision: str = "b7c8d9e0f1a2"
down_revision: str | Sequence[str] | None = "a6b7c8d9e0f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Member and available-student search uses ILIKE on these two fields.
    # Trigram indexes keep substring search bounded without widening the tenant
    # predicate, which remains the leading filter in the application query.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_index("ix_users_full_name_trgm", "users", ["full_name"], postgresql_using="gin", postgresql_ops={"full_name": "gin_trgm_ops"})
    op.create_index("ix_users_email_trgm", "users", ["email"], postgresql_using="gin", postgresql_ops={"email": "gin_trgm_ops"})

    op.create_index("ix_reports_org_student_created_id", "reports", ["organization_id", "student_id", "created_at", "id"])
    op.create_index("ix_reports_org_internship_created_id", "reports", ["organization_id", "internship_id", "created_at", "id"])
    op.create_index("ix_internships_org_group_created_id", "internships", ["organization_id", "group_id", "created_at", "id"])
    op.create_index("ix_templates_org_name_id", "templates", ["organization_id", "name", "id"])
    op.create_index("ix_notifications_org_user_created_id", "notifications", ["organization_id", "user_id", "created_at", "id"])
    op.create_index("ix_comments_org_report_parent_created_id", "comments", ["organization_id", "report_id", "parent_comment_id", "created_at", "id"])
    op.create_index("ix_audit_logs_org_entity_created_id", "audit_logs", ["organization_id", "entity_type", "entity_id", "created_at", "id"])
    op.create_index("ix_memberships_org_created_id", "organization_memberships", ["organization_id", "created_at", "id"])
    op.create_index("ix_memberships_user_active_org", "organization_memberships", ["user_id", "is_active", "organization_id"])
    op.create_index("ix_group_members_group_id_id", "group_members", ["group_id", "id"])
    op.create_index("ix_organizations_name_id", "organizations", ["name", "id"])


def downgrade() -> None:
    op.drop_index("ix_organizations_name_id", table_name="organizations")
    op.drop_index("ix_group_members_group_id_id", table_name="group_members")
    op.drop_index("ix_memberships_user_active_org", table_name="organization_memberships")
    op.drop_index("ix_memberships_org_created_id", table_name="organization_memberships")
    op.drop_index("ix_audit_logs_org_entity_created_id", table_name="audit_logs")
    op.drop_index("ix_comments_org_report_parent_created_id", table_name="comments")
    op.drop_index("ix_notifications_org_user_created_id", table_name="notifications")
    op.drop_index("ix_templates_org_name_id", table_name="templates")
    op.drop_index("ix_internships_org_group_created_id", table_name="internships")
    op.drop_index("ix_reports_org_internship_created_id", table_name="reports")
    op.drop_index("ix_reports_org_student_created_id", table_name="reports")
    op.drop_index("ix_users_email_trgm", table_name="users")
    op.drop_index("ix_users_full_name_trgm", table_name="users")
    # The extension can be shared with other database features, so downgrade
    # deliberately leaves it installed rather than risking an unsafe drop.
