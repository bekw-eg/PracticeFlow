"""Teacher-owned disciplines, topics, existing group links and private materials."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "6e7f8091a2b3"
down_revision = "5d6e7f8091a2"
branch_labels = None
depends_on = None


def identity():
    return [sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())]


def upgrade():
    op.create_table("disciplines", *identity(),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("academic_year", sa.String(20)),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id", "organization_id"],
            ["organization_memberships.user_id", "organization_memberships.organization_id"],
            ondelete="RESTRICT", name="fk_discipline_owner_membership"),
        sa.UniqueConstraint("organization_id", "id", name="uq_disciplines_org_id"))
    op.create_index("ix_disciplines_owner_archive", "disciplines",
                    ["organization_id", "created_by_user_id", "is_archived", "created_at", "id"])
    op.create_table("discipline_groups",
        sa.Column("organization_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("discipline_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("group_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.ForeignKeyConstraint(["organization_id", "discipline_id"], ["disciplines.organization_id", "disciplines.id"],
                                ondelete="CASCADE", name="fk_discipline_group_discipline"),
        sa.ForeignKeyConstraint(["organization_id", "group_id"], ["groups.organization_id", "groups.id"],
                                ondelete="CASCADE", name="fk_discipline_group_group"))
    op.create_index("ix_discipline_groups_group", "discipline_groups", ["organization_id", "group_id"])
    op.create_table("discipline_topics", *identity(),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("discipline_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("learning_goal", sa.Text()),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(["organization_id", "discipline_id"], ["disciplines.organization_id", "disciplines.id"],
                                ondelete="RESTRICT", name="fk_topic_discipline"),
        sa.UniqueConstraint("organization_id", "discipline_id", "id", name="uq_topics_org_discipline_id"),
        sa.CheckConstraint("position >= 0", name="ck_topic_position"))
    op.create_index("ix_topics_discipline_position", "discipline_topics",
                    ["organization_id", "discipline_id", "is_archived", "position", "id"])
    op.create_table("teaching_materials", *identity(),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("discipline_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("topic_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("uploaded_by_user_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column("content_type", sa.String(127), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("storage_deleted_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["organization_id", "discipline_id", "topic_id"],
            ["discipline_topics.organization_id", "discipline_topics.discipline_id", "discipline_topics.id"],
            ondelete="RESTRICT", name="fk_material_topic"),
        sa.ForeignKeyConstraint(["uploaded_by_user_id", "organization_id"],
            ["organization_memberships.user_id", "organization_memberships.organization_id"],
            ondelete="RESTRICT", name="fk_material_uploader_membership"),
        sa.UniqueConstraint("storage_key", name="uq_teaching_material_storage_key"),
        sa.UniqueConstraint("organization_id", "topic_id", "uploaded_by_user_id", "idempotency_key",
                            name="uq_material_upload_request"),
        sa.CheckConstraint("size_bytes > 0", name="ck_material_size"),
        sa.CheckConstraint("storage_deleted_at IS NULL OR deleted_at IS NOT NULL", name="ck_material_deletion"))
    op.create_index("ix_materials_topic_created", "teaching_materials",
                    ["organization_id", "topic_id", "deleted_at", "created_at", "id"])


def downgrade():
    # Intentionally destructive for this additive domain. Back up private
    # materials before downgrade; storage objects require separate reconciliation.
    op.drop_table("teaching_materials")
    op.drop_table("discipline_topics")
    op.drop_table("discipline_groups")
    op.drop_table("disciplines")
