"""Teacher-owned direct DOCX checks.

Revision ID: 0c4d5e6f7a8b
Revises: fb3a4b5c6d7e
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0c4d5e6f7a8b"
down_revision = "fb3a4b5c6d7e"
branch_labels = None
depends_on = None


def _timestamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def install_teacher_submission_guards() -> None:
    op.execute("""
    CREATE OR REPLACE FUNCTION pf_protect_teacher_original() RETURNS trigger AS $$
    BEGIN
      RAISE EXCEPTION 'teacher document submissions are immutable' USING ERRCODE = '23514';
    END;
    $$ LANGUAGE plpgsql;
    CREATE TRIGGER trg_protect_teacher_original
      BEFORE UPDATE OR DELETE ON teacher_document_submissions
      FOR EACH ROW EXECUTE FUNCTION pf_protect_teacher_original();

    CREATE OR REPLACE FUNCTION pf_validate_teacher_submission() RETURNS trigger AS $$
    BEGIN
      IF NOT EXISTS (
        SELECT 1 FROM teachers t
        JOIN organization_memberships m ON m.id = t.membership_id
        WHERE t.id = NEW.teacher_id AND m.organization_id = NEW.organization_id
      ) THEN
        RAISE EXCEPTION 'teacher submission owner must belong to its tenant' USING ERRCODE = '23514';
      END IF;
      IF NOT EXISTS (
        SELECT 1 FROM check_profile_versions v
        WHERE v.id = NEW.profile_version_id AND v.organization_id = NEW.organization_id
          AND v.state = 'PUBLISHED'
      ) THEN
        RAISE EXCEPTION 'teacher submission requires a published tenant profile version'
          USING ERRCODE = '23514';
      END IF;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    CREATE TRIGGER trg_validate_teacher_submission
      BEFORE INSERT ON teacher_document_submissions
      FOR EACH ROW EXECUTE FUNCTION pf_validate_teacher_submission();

    CREATE OR REPLACE FUNCTION pf_require_teacher_submission_job() RETURNS trigger AS $$
    BEGIN
      IF NOT EXISTS (
        SELECT 1 FROM document_check_jobs j
        WHERE j.organization_id = NEW.organization_id AND j.teacher_submission_id = NEW.id
      ) THEN
        RAISE EXCEPTION 'a teacher submission must have exactly one check job' USING ERRCODE = '23514';
      END IF;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    CREATE CONSTRAINT TRIGGER trg_require_teacher_submission_job
      AFTER INSERT ON teacher_document_submissions DEFERRABLE INITIALLY DEFERRED
      FOR EACH ROW EXECUTE FUNCTION pf_require_teacher_submission_job();
    """)


def upgrade() -> None:
    for value in (
        "TEACHER_DOCUMENT_CHECK_UPLOADED",
        "TEACHER_DOCUMENT_CHECK_DOWNLOADED",
        "TEACHER_DOCUMENT_CHECK_REJECTED",
    ):
        op.execute(f"ALTER TYPE audit_event_type ADD VALUE IF NOT EXISTS '{value}'")

    op.create_table(
        "teacher_document_submissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("teacher_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("profile_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_label", sa.String(255), nullable=True),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("storage_key", sa.String(1024), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("detected_mime", sa.String(100), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("preflight_schema_version", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["teacher_id"], ["teachers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["organization_id", "profile_version_id"],
            ["check_profile_versions.organization_id", "check_profile_versions.id"],
            name="fk_teacher_submissions_version_tenant", ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("organization_id", "id", name="uq_teacher_submissions_org_id"),
        sa.UniqueConstraint(
            "organization_id", "teacher_id", "idempotency_key",
            name="uq_teacher_submissions_idempotency",
        ),
        sa.UniqueConstraint("storage_key", name="uq_teacher_submissions_storage_key"),
        sa.CheckConstraint("size_bytes > 0", name="ck_teacher_submissions_size_positive"),
        sa.CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="ck_teacher_submissions_sha256"),
        sa.CheckConstraint("preflight_schema_version = 1", name="ck_teacher_submissions_preflight_version"),
        sa.CheckConstraint(
            "length(idempotency_key) BETWEEN 1 AND 128", name="ck_teacher_submissions_idempotency_key"
        ),
        sa.CheckConstraint(
            "student_label IS NULL OR length(btrim(student_label)) BETWEEN 1 AND 255",
            name="ck_teacher_submissions_student_label",
        ),
        sa.CheckConstraint(
            "detected_mime = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'",
            name="ck_teacher_submissions_docx_mime",
        ),
    )
    op.create_index(
        "ix_teacher_submissions_org_teacher_submitted", "teacher_document_submissions",
        ["organization_id", "teacher_id", "submitted_at", "id"],
    )

    op.alter_column("document_check_jobs", "submission_id", existing_type=postgresql.UUID(), nullable=True)
    op.add_column(
        "document_check_jobs",
        sa.Column("teacher_submission_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_check_jobs_teacher_submission_tenant", "document_check_jobs", "teacher_document_submissions",
        ["organization_id", "teacher_submission_id"], ["organization_id", "id"], ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_check_jobs_teacher_submission", "document_check_jobs", ["organization_id", "teacher_submission_id"]
    )
    op.create_check_constraint(
        "ck_check_jobs_exactly_one_submission", "document_check_jobs",
        "(submission_id IS NULL) <> (teacher_submission_id IS NULL)",
    )
    install_teacher_submission_guards()


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_require_teacher_submission_job ON teacher_document_submissions")
    op.execute("DROP TRIGGER IF EXISTS trg_validate_teacher_submission ON teacher_document_submissions")
    op.execute("DROP TRIGGER IF EXISTS trg_protect_teacher_original ON teacher_document_submissions")
    for name in (
        "pf_require_teacher_submission_job", "pf_validate_teacher_submission", "pf_protect_teacher_original",
    ):
        op.execute(f"DROP FUNCTION IF EXISTS {name}()")
    op.drop_constraint("ck_check_jobs_exactly_one_submission", "document_check_jobs", type_="check")
    op.drop_constraint("uq_check_jobs_teacher_submission", "document_check_jobs", type_="unique")
    op.drop_constraint("fk_check_jobs_teacher_submission_tenant", "document_check_jobs", type_="foreignkey")
    op.drop_column("document_check_jobs", "teacher_submission_id")
    op.alter_column("document_check_jobs", "submission_id", existing_type=postgresql.UUID(), nullable=False)
    op.drop_index("ix_teacher_submissions_org_teacher_submitted", table_name="teacher_document_submissions")
    op.drop_table("teacher_document_submissions")
    # Audit enum labels remain available for historical rows.
