"""Private presentation snapshots and drafts; additive to completed reviews."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "5d6e7f8091a2"
down_revision = "4c5d6e7f8091"
branch_labels = None
depends_on = None


def install_report_guards():
    op.execute("""
    CREATE FUNCTION pf_protect_group_review_report() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF OLD.snapshot IS DISTINCT FROM NEW.snapshot OR
         (OLD.organization_id, OLD.teacher_id, OLD.group_id, OLD.request_id, OLD.locale, OLD.created_at)
         IS DISTINCT FROM
         (NEW.organization_id, NEW.teacher_id, NEW.group_id, NEW.request_id, NEW.locale, NEW.created_at) THEN
        RAISE EXCEPTION 'Group report evidence and identity are immutable';
      END IF;
      IF OLD.generated_at IS NOT NULL AND OLD IS DISTINCT FROM NEW THEN
        RAISE EXCEPTION 'Generated group reports are immutable';
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER trg_protect_group_review_report BEFORE UPDATE ON group_review_reports
      FOR EACH ROW EXECUTE FUNCTION pf_protect_group_review_report();
    """)


def upgrade():
    op.create_table("group_review_reports",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("teacher_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("group_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("request_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("locale", sa.String(2), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("snapshot", pg.JSONB(), nullable=False),
        sa.Column("content", pg.JSONB(), nullable=False),
        sa.Column("storage_key", sa.String(512)),
        sa.Column("generated_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id", "teacher_id", "group_id"],
            ["review_groups.organization_id", "review_groups.teacher_id", "review_groups.id"],
            ondelete="RESTRICT", name="fk_group_review_report_owner"),
        sa.UniqueConstraint("organization_id", "teacher_id", "group_id", "request_id", name="uq_group_report_request"),
        sa.CheckConstraint("revision > 0", name="ck_group_report_revision"),
        sa.CheckConstraint("locale IN ('ru', 'kk', 'en')", name="ck_group_report_locale"),
        sa.CheckConstraint("jsonb_typeof(snapshot) = 'object' AND jsonb_typeof(content) = 'object'", name="ck_group_report_json"),
        sa.CheckConstraint("(storage_key IS NULL AND generated_at IS NULL) OR "
                           "(storage_key IS NOT NULL AND generated_at IS NOT NULL)", name="ck_group_report_generated"),
    )
    op.create_index("ix_group_review_reports_organization_id", "group_review_reports", ["organization_id"])
    op.create_index("ix_group_review_reports_group_id", "group_review_reports", ["group_id"])
    install_report_guards()


def downgrade():
    op.drop_table("group_review_reports")
    op.execute("DROP FUNCTION pf_protect_group_review_report()")
