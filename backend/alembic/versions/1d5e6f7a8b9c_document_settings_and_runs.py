"""Document-owned settings and immutable recheck snapshots.

Revision ID: 1d5e6f7a8b9c
Revises: 0c4d5e6f7a8b
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "1d5e6f7a8b9c"
down_revision = "0c4d5e6f7a8b"
branch_labels = None
depends_on = None


def _timestamps():
    return [sa.Column(name, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
            for name in ("created_at", "updated_at")]


def upgrade():
    op.create_table(
        "document_check_settings",
        sa.Column("organization_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("submission_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("rules", pg.JSONB(), nullable=False),
        sa.Column("paragraph_overrides", pg.JSONB(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["organization_id", "submission_id"],
                                ["teacher_document_submissions.organization_id", "teacher_document_submissions.id"],
                                name="fk_document_settings_submission", ondelete="RESTRICT"),
        sa.CheckConstraint("revision > 0", name="ck_document_settings_revision"),
        sa.CheckConstraint("jsonb_typeof(rules) = 'array'", name="ck_document_settings_rules"),
        sa.CheckConstraint("jsonb_typeof(paragraph_overrides) = 'object'", name="ck_document_settings_overrides"),
    )
    op.add_column("document_check_jobs", sa.Column("run_number", sa.Integer(), server_default="1", nullable=False))
    op.add_column("document_check_jobs", sa.Column("idempotency_key", sa.String(128), nullable=True))
    op.add_column("document_check_jobs", sa.Column("settings_snapshot", pg.JSONB(), nullable=True))
    op.drop_constraint("uq_check_jobs_teacher_submission", "document_check_jobs", type_="unique")
    op.create_unique_constraint("uq_check_jobs_teacher_run", "document_check_jobs",
                                ["organization_id", "teacher_submission_id", "run_number"])
    op.create_unique_constraint("uq_check_jobs_teacher_key", "document_check_jobs",
                                ["organization_id", "teacher_submission_id", "idempotency_key"])
    op.create_check_constraint("ck_check_jobs_run_positive", "document_check_jobs", "run_number > 0")
    op.create_check_constraint("ck_check_jobs_snapshot_object", "document_check_jobs",
                               "settings_snapshot IS NULL OR jsonb_typeof(settings_snapshot) = 'object'")
    op.create_table(
        "document_check_run_rules",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("rule_type", pg.ENUM(name="check_rule_type", create_type=False), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("severity", pg.ENUM(name="check_rule_severity", create_type=False), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("config_schema_version", sa.Integer(), nullable=False),
        sa.Column("config", pg.JSONB(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["organization_id", "job_id"],
                                ["document_check_jobs.organization_id", "document_check_jobs.id"],
                                name="fk_run_rules_job", ondelete="RESTRICT"),
        sa.UniqueConstraint("organization_id", "job_id", "id", name="uq_run_rules_job_id"),
        sa.UniqueConstraint("organization_id", "job_id", "sort_order", name="uq_run_rules_order"),
        sa.CheckConstraint("jsonb_typeof(config) = 'object'", name="ck_run_rules_config"),
    )
    op.alter_column("document_check_findings", "check_rule_id", existing_type=pg.UUID(), nullable=True)
    op.add_column("document_check_findings", sa.Column("run_rule_id", pg.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_check_findings_run_rule", "document_check_findings", "document_check_run_rules",
                          ["organization_id", "job_id", "run_rule_id"], ["organization_id", "job_id", "id"],
                          ondelete="RESTRICT")
    op.create_check_constraint("ck_findings_rule_identity", "document_check_findings",
                               "(check_rule_id IS NULL) <> (run_rule_id IS NULL)")
    install_document_settings_guards()


def install_document_settings_guards():
    # Existing job guard compares every identity column, so it also protects the
    # new snapshot/key/run number without modifying historical jobs or results.
    op.execute("""
    CREATE FUNCTION pf_protect_run_rule() RETURNS trigger AS $$
    BEGIN
      IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'run rules are immutable' USING ERRCODE = '23514';
      END IF;
      IF NOT EXISTS (
        SELECT 1 FROM document_check_jobs j,
          jsonb_array_elements(j.settings_snapshot->'rules') r
        WHERE j.organization_id = NEW.organization_id AND j.id = NEW.job_id
          AND j.status = 'QUEUED'
          AND r = (to_jsonb(NEW) - ARRAY['organization_id','job_id','created_at','updated_at'])
      ) THEN
        RAISE EXCEPTION 'run rule must match its sealed job snapshot' USING ERRCODE = '23514';
      END IF;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    CREATE TRIGGER trg_protect_run_rule BEFORE INSERT OR UPDATE OR DELETE ON document_check_run_rules
      FOR EACH ROW EXECUTE FUNCTION pf_protect_run_rule();

    CREATE OR REPLACE FUNCTION pf_validate_document_check_finding() RETURNS trigger AS $$
    DECLARE snapshot jsonb;
    BEGIN
      IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'document check findings are immutable' USING ERRCODE = '23514';
      END IF;
      SELECT j.settings_snapshot INTO snapshot FROM document_check_jobs j
        WHERE j.organization_id = NEW.organization_id AND j.id = NEW.job_id AND j.status = 'PROCESSING';
      IF NOT FOUND THEN
        RAISE EXCEPTION 'findings require a processing tenant job' USING ERRCODE = '23514';
      END IF;
      IF snapshot IS NOT NULL THEN
        IF NEW.check_rule_id IS NOT NULL OR NOT EXISTS (
          SELECT 1 FROM document_check_run_rules r WHERE r.organization_id = NEW.organization_id
            AND r.job_id = NEW.job_id AND r.id = NEW.run_rule_id AND r.enabled
            AND r.rule_type = NEW.rule_type AND r.category = NEW.category AND r.severity = NEW.severity
        ) THEN
          RAISE EXCEPTION 'finding must reference an enabled rule of its snapshot' USING ERRCODE = '23514';
        END IF;
      ELSIF NEW.run_rule_id IS NOT NULL THEN
        RAISE EXCEPTION 'legacy findings require a global rule identity' USING ERRCODE = '23514';
      END IF;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    CREATE OR REPLACE FUNCTION pf_require_teacher_submission_job() RETURNS trigger AS $$
    BEGIN
      IF NOT EXISTS (SELECT 1 FROM document_check_jobs j
        WHERE j.organization_id = NEW.organization_id AND j.teacher_submission_id = NEW.id) THEN
        RAISE EXCEPTION 'a teacher submission must have at least one check job' USING ERRCODE = '23514';
      END IF;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)


def downgrade():
    # Never silently erase saved settings or immutable run history on rollback.
    op.execute("""
    DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM document_check_settings)
         OR EXISTS (SELECT 1 FROM document_check_jobs WHERE settings_snapshot IS NOT NULL OR run_number > 1) THEN
        RAISE EXCEPTION 'Cannot downgrade with document settings or rechecks; preserve data and roll forward';
      END IF;
    END $$;
    """)
    op.execute("""
    CREATE OR REPLACE FUNCTION pf_validate_document_check_finding() RETURNS trigger AS $$
    BEGIN
      IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'document check findings are immutable' USING ERRCODE = '23514';
      END IF;
      IF NOT EXISTS (SELECT 1 FROM document_check_jobs j
        WHERE j.organization_id = NEW.organization_id AND j.id = NEW.job_id AND j.status = 'PROCESSING') THEN
        RAISE EXCEPTION 'findings require a processing tenant job' USING ERRCODE = '23514';
      END IF;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)
    op.drop_constraint("ck_findings_rule_identity", "document_check_findings", type_="check")
    op.drop_constraint("fk_check_findings_run_rule", "document_check_findings", type_="foreignkey")
    op.drop_column("document_check_findings", "run_rule_id")
    op.alter_column("document_check_findings", "check_rule_id", existing_type=pg.UUID(), nullable=False)
    op.execute("DROP TRIGGER trg_protect_run_rule ON document_check_run_rules")
    op.execute("DROP FUNCTION pf_protect_run_rule()")
    op.drop_table("document_check_run_rules")
    for name in ("ck_check_jobs_run_positive", "ck_check_jobs_snapshot_object"):
        op.drop_constraint(name, "document_check_jobs", type_="check")
    for name in ("uq_check_jobs_teacher_run", "uq_check_jobs_teacher_key"):
        op.drop_constraint(name, "document_check_jobs", type_="unique")
    op.create_unique_constraint("uq_check_jobs_teacher_submission", "document_check_jobs",
                                ["organization_id", "teacher_submission_id"])
    for name in ("settings_snapshot", "idempotency_key", "run_number"):
        op.drop_column("document_check_jobs", name)
    op.drop_table("document_check_settings")
