"""Document analyzer execution metadata and immutable structured findings.

Revision ID: fb3a4b5c6d7e
Revises: ea2f3a4b5c6d
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "fb3a4b5c6d7e"
down_revision = "ea2f3a4b5c6d"
branch_labels = None
depends_on = None

check_rule_type = postgresql.ENUM(
    "PAGE_FORMAT_MARGINS", "FONTS_SIZES", "PARAGRAPH_SPACING_INDENTS", "HEADINGS",
    "TABLES", "FIGURE_CAPTIONS", "REFERENCES", "REQUIRED_SECTIONS", "SPELLING_LANGUAGES",
    name="check_rule_type", create_type=False,
)
check_rule_severity = postgresql.ENUM("INFO", "WARNING", "ERROR", name="check_rule_severity", create_type=False)


def _timestamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def install_analyzer_guards() -> None:
    op.execute("""
    CREATE OR REPLACE FUNCTION pf_protect_check_job_identity() RETURNS trigger AS $$
    BEGIN
      IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'check jobs cannot be deleted' USING ERRCODE = '23514';
      END IF;
      IF (to_jsonb(NEW) - ARRAY[
            'status','started_at','finished_at','error_code','error_message','updated_at',
            'analyzer_version','attempt_count','worker_id','lease_expires_at','result_summary'
          ]) IS DISTINCT FROM
         (to_jsonb(OLD) - ARRAY[
            'status','started_at','finished_at','error_code','error_message','updated_at',
            'analyzer_version','attempt_count','worker_id','lease_expires_at','result_summary'
          ]) THEN
        RAISE EXCEPTION 'check job identity is immutable' USING ERRCODE = '23514';
      END IF;
      IF OLD.status IN ('COMPLETED', 'FAILED') THEN
        RAISE EXCEPTION 'terminal check jobs are immutable' USING ERRCODE = '23514';
      ELSIF OLD.status = 'QUEUED' AND NEW.status <> 'PROCESSING' THEN
        RAISE EXCEPTION 'queued check job must transition to processing' USING ERRCODE = '23514';
      ELSIF OLD.status = 'PROCESSING' AND NEW.status NOT IN ('PROCESSING', 'QUEUED', 'COMPLETED', 'FAILED') THEN
        RAISE EXCEPTION 'invalid processing check job transition' USING ERRCODE = '23514';
      END IF;
      IF NEW.attempt_count < OLD.attempt_count OR NEW.attempt_count > OLD.attempt_count + 1 THEN
        RAISE EXCEPTION 'invalid check job attempt count' USING ERRCODE = '23514';
      END IF;
      IF OLD.status = 'QUEUED' AND NEW.status = 'PROCESSING' AND NEW.attempt_count <> OLD.attempt_count + 1 THEN
        RAISE EXCEPTION 'claim must increment check job attempt count' USING ERRCODE = '23514';
      END IF;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    CREATE FUNCTION pf_validate_document_check_finding() RETURNS trigger AS $$
    BEGIN
      IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'document check findings are immutable' USING ERRCODE = '23514';
      END IF;
      IF NOT EXISTS (
        SELECT 1 FROM document_check_jobs j
        WHERE j.organization_id = NEW.organization_id AND j.id = NEW.job_id
          AND j.status = 'PROCESSING'
      ) THEN
        RAISE EXCEPTION 'findings require a processing tenant job' USING ERRCODE = '23514';
      END IF;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    CREATE TRIGGER trg_validate_document_check_finding
      BEFORE INSERT OR UPDATE OR DELETE ON document_check_findings
      FOR EACH ROW EXECUTE FUNCTION pf_validate_document_check_finding();
    """)


def upgrade() -> None:
    for value in ("DOCUMENT_CHECK_JOB_STARTED", "DOCUMENT_CHECK_JOB_COMPLETED", "DOCUMENT_CHECK_JOB_FAILED"):
        op.execute(f"ALTER TYPE audit_event_type ADD VALUE IF NOT EXISTS '{value}'")
    op.add_column("document_check_jobs", sa.Column("analyzer_version", sa.String(50), nullable=True))
    op.add_column("document_check_jobs", sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False))
    op.add_column("document_check_jobs", sa.Column("worker_id", sa.String(128), nullable=True))
    op.add_column("document_check_jobs", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("document_check_jobs", sa.Column("result_summary", postgresql.JSONB(), nullable=True))
    op.drop_constraint("ck_check_jobs_status_timestamps", "document_check_jobs", type_="check")
    op.create_check_constraint(
        "ck_check_jobs_status_timestamps", "document_check_jobs",
        "(status = 'QUEUED' AND started_at IS NULL AND finished_at IS NULL AND worker_id IS NULL AND lease_expires_at IS NULL) OR "
        "(status = 'PROCESSING' AND started_at IS NOT NULL AND finished_at IS NULL AND worker_id IS NOT NULL AND lease_expires_at IS NOT NULL) OR "
        "(status = 'COMPLETED' AND started_at IS NOT NULL AND finished_at IS NOT NULL AND worker_id IS NULL AND lease_expires_at IS NULL AND result_summary IS NOT NULL) OR "
        "(status = 'FAILED' AND finished_at IS NOT NULL AND worker_id IS NULL AND lease_expires_at IS NULL)",
    )
    op.create_check_constraint("ck_check_jobs_attempt_count", "document_check_jobs", "attempt_count >= 0")
    op.create_check_constraint(
        "ck_check_jobs_result_summary", "document_check_jobs",
        "result_summary IS NULL OR jsonb_typeof(result_summary) = 'object'",
    )
    op.create_table(
        "document_check_findings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("check_rule_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("rule_type", check_rule_type, nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("severity", check_rule_severity, nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("property_name", sa.String(80), nullable=False),
        sa.Column("location", postgresql.JSONB(), nullable=False),
        sa.Column("expected", postgresql.JSONB(), nullable=False),
        sa.Column("actual", postgresql.JSONB(), nullable=False),
        sa.Column("finding_schema_version", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["organization_id", "job_id"],
            ["document_check_jobs.organization_id", "document_check_jobs.id"],
            name="fk_check_findings_job_tenant", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "check_rule_id"],
            ["check_rules.organization_id", "check_rules.id"],
            name="fk_check_findings_rule_tenant", ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("organization_id", "id", name="uq_check_findings_org_id"),
        sa.UniqueConstraint("organization_id", "job_id", "sequence", name="uq_check_findings_sequence"),
        sa.CheckConstraint("sequence > 0", name="ck_check_findings_sequence_positive"),
        sa.CheckConstraint("finding_schema_version = 1", name="ck_check_findings_schema_version"),
        sa.CheckConstraint("jsonb_typeof(location) = 'object'", name="ck_check_findings_location_object"),
        sa.CheckConstraint("jsonb_typeof(expected) = 'object'", name="ck_check_findings_expected_object"),
        sa.CheckConstraint("jsonb_typeof(actual) = 'object'", name="ck_check_findings_actual_object"),
    )
    op.create_index(
        "ix_check_findings_org_job_sequence", "document_check_findings",
        ["organization_id", "job_id", "sequence"],
    )
    install_analyzer_guards()


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_validate_document_check_finding ON document_check_findings")
    op.execute("DROP FUNCTION IF EXISTS pf_validate_document_check_finding()")
    op.drop_index("ix_check_findings_org_job_sequence", table_name="document_check_findings")
    op.drop_table("document_check_findings")
    op.execute("""
    CREATE OR REPLACE FUNCTION pf_protect_check_job_identity() RETURNS trigger AS $$
    BEGIN
      IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'check jobs cannot be deleted' USING ERRCODE = '23514';
      END IF;
      IF (to_jsonb(NEW) - ARRAY['status','started_at','finished_at','error_code','error_message','updated_at'])
        IS DISTINCT FROM
         (to_jsonb(OLD) - ARRAY['status','started_at','finished_at','error_code','error_message','updated_at']) THEN
        RAISE EXCEPTION 'check job identity is immutable' USING ERRCODE = '23514';
      END IF;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)
    op.drop_constraint("ck_check_jobs_result_summary", "document_check_jobs", type_="check")
    op.drop_constraint("ck_check_jobs_attempt_count", "document_check_jobs", type_="check")
    op.drop_constraint("ck_check_jobs_status_timestamps", "document_check_jobs", type_="check")
    op.drop_column("document_check_jobs", "result_summary")
    op.drop_column("document_check_jobs", "lease_expires_at")
    op.drop_column("document_check_jobs", "worker_id")
    op.drop_column("document_check_jobs", "attempt_count")
    op.drop_column("document_check_jobs", "analyzer_version")
    op.create_check_constraint(
        "ck_check_jobs_status_timestamps", "document_check_jobs",
        "(status = 'QUEUED' AND started_at IS NULL AND finished_at IS NULL) OR "
        "(status = 'PROCESSING' AND started_at IS NOT NULL AND finished_at IS NULL) OR "
        "(status = 'COMPLETED' AND started_at IS NOT NULL AND finished_at IS NOT NULL) OR "
        "(status = 'FAILED' AND finished_at IS NOT NULL)",
    )
    # Append-only audit enum labels remain for historical rows.
