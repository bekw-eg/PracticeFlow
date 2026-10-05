"""Immutable student DOCX originals and a separate queued check job.

Revision ID: ea2f3a4b5c6d
Revises: da1e2f3a4b5c
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "ea2f3a4b5c6d"
down_revision = "da1e2f3a4b5c"
branch_labels = None
depends_on = None

job_status = postgresql.ENUM("QUEUED", "PROCESSING", "COMPLETED", "FAILED",
                             name="document_check_job_status", create_type=False)


def _timestamps():
    return [sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)]


def install_guards() -> None:
    # Frozen migration SQL, also exercised by the direct-metadata test fixture.
    op.execute("""
    CREATE FUNCTION pf_protect_student_original() RETURNS trigger AS $$
    BEGIN
      RAISE EXCEPTION 'student document submissions are immutable' USING ERRCODE = '23514';
    END;
    $$ LANGUAGE plpgsql;
    CREATE TRIGGER trg_protect_student_original BEFORE UPDATE OR DELETE ON student_document_submissions
      FOR EACH ROW EXECUTE FUNCTION pf_protect_student_original();

    CREATE FUNCTION pf_validate_student_submission() RETURNS trigger AS $$
    DECLARE assignment_state document_check_assignment_status;
    DECLARE deadline timestamptz;
    DECLARE next_attempt integer;
    BEGIN
      -- Share-lock publication state so a concurrent close cannot race acceptance.
      SELECT state, due_at INTO assignment_state, deadline FROM document_check_assignments
        WHERE organization_id = NEW.organization_id AND id = NEW.assignment_id FOR SHARE;
      IF assignment_state IS DISTINCT FROM 'PUBLISHED' THEN
        RAISE EXCEPTION 'assignment is not published' USING ERRCODE = '23514';
      END IF;
      PERFORM 1 FROM assignment_students
        WHERE organization_id = NEW.organization_id AND id = NEW.assignment_student_id
          AND assignment_id = NEW.assignment_id AND student_id = NEW.student_id FOR UPDATE;
      IF NOT FOUND THEN
        RAISE EXCEPTION 'submission must reference its exact tenant roster entry' USING ERRCODE = '23514';
      END IF;
      SELECT coalesce(max(attempt_number), 0) + 1 INTO next_attempt FROM student_document_submissions
        WHERE organization_id = NEW.organization_id AND assignment_student_id = NEW.assignment_student_id;
      IF NEW.attempt_number <> next_attempt THEN
        RAISE EXCEPTION 'submission attempt must be sequential' USING ERRCODE = '23514';
      END IF;
      IF NEW.is_late IS DISTINCT FROM (NEW.submitted_at > deadline) THEN
        RAISE EXCEPTION 'incorrect submission late status' USING ERRCODE = '23514';
      END IF;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    CREATE TRIGGER trg_validate_student_submission BEFORE INSERT ON student_document_submissions
      FOR EACH ROW EXECUTE FUNCTION pf_validate_student_submission();

    CREATE FUNCTION pf_require_submission_job() RETURNS trigger AS $$
    BEGIN
      IF NOT EXISTS (SELECT 1 FROM document_check_jobs
        WHERE organization_id = NEW.organization_id AND submission_id = NEW.id) THEN
        RAISE EXCEPTION 'a submission must have exactly one check job' USING ERRCODE = '23514';
      END IF;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    CREATE CONSTRAINT TRIGGER trg_require_submission_job AFTER INSERT ON student_document_submissions
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION pf_require_submission_job();

    CREATE FUNCTION pf_protect_check_job_identity() RETURNS trigger AS $$
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
    CREATE TRIGGER trg_protect_check_job_identity BEFORE UPDATE OR DELETE ON document_check_jobs
      FOR EACH ROW EXECUTE FUNCTION pf_protect_check_job_identity();
    """)


def upgrade() -> None:
    for value in ("DOCUMENT_SUBMISSION_UPLOADED", "DOCUMENT_SUBMISSION_STUDENT_DOWNLOADED",
                  "DOCUMENT_SUBMISSION_TEACHER_DOWNLOADED", "DOCUMENT_SUBMISSION_REJECTED",
                  "DOCUMENT_CHECK_JOB_CREATED"):
        op.execute(f"ALTER TYPE audit_event_type ADD VALUE IF NOT EXISTS '{value}'")
    job_status.create(op.get_bind(), checkfirst=True)
    op.create_unique_constraint("uq_assignment_students_submission_target", "assignment_students",
                                ["organization_id", "id", "assignment_id", "student_id"])
    op.create_table(
        "student_document_submissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assignment_student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("storage_key", sa.String(1024), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("detected_mime", sa.String(100), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_late", sa.Boolean(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("preflight_schema_version", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id", "assignment_id"],
            ["document_check_assignments.organization_id", "document_check_assignments.id"],
            name="fk_submissions_assignment_tenant", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id", "assignment_student_id", "assignment_id", "student_id"],
            ["assignment_students.organization_id", "assignment_students.id",
             "assignment_students.assignment_id", "assignment_students.student_id"],
            name="fk_submissions_exact_roster_tenant", ondelete="RESTRICT"),
        sa.UniqueConstraint("organization_id", "id", name="uq_submissions_org_id"),
        sa.UniqueConstraint("organization_id", "assignment_student_id", "attempt_number", name="uq_submissions_attempt"),
        sa.UniqueConstraint("organization_id", "assignment_student_id", "idempotency_key", name="uq_submissions_idempotency"),
        sa.UniqueConstraint("storage_key", name="uq_submissions_storage_key"),
        sa.CheckConstraint("attempt_number > 0", name="ck_submissions_attempt_positive"),
        sa.CheckConstraint("size_bytes > 0", name="ck_submissions_size_positive"),
        sa.CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="ck_submissions_sha256"),
        sa.CheckConstraint("preflight_schema_version = 1", name="ck_submissions_preflight_version"),
        sa.CheckConstraint("length(idempotency_key) BETWEEN 1 AND 128", name="ck_submissions_idempotency_key"),
        sa.CheckConstraint("detected_mime = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'",
                           name="ck_submissions_docx_mime"),
    )
    op.create_index("ix_submissions_org_assignment_student", "student_document_submissions",
                    ["organization_id", "assignment_id", "student_id", "attempt_number"])
    op.create_table(
        "document_check_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("submission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", job_status, nullable=False),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(80)),
        sa.Column("error_message", sa.String(500)),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id", "submission_id"],
            ["student_document_submissions.organization_id", "student_document_submissions.id"],
            name="fk_check_jobs_submission_tenant", ondelete="RESTRICT"),
        sa.UniqueConstraint("organization_id", "id", name="uq_check_jobs_org_id"),
        sa.UniqueConstraint("organization_id", "submission_id", name="uq_check_jobs_submission"),
        sa.CheckConstraint(
            "(status = 'QUEUED' AND started_at IS NULL AND finished_at IS NULL) OR "
            "(status = 'PROCESSING' AND started_at IS NOT NULL AND finished_at IS NULL) OR "
            "(status = 'COMPLETED' AND started_at IS NOT NULL AND finished_at IS NOT NULL) OR "
            "(status = 'FAILED' AND finished_at IS NOT NULL)", name="ck_check_jobs_status_timestamps"),
        sa.CheckConstraint("started_at IS NULL OR started_at >= queued_at", name="ck_check_jobs_started_at"),
        sa.CheckConstraint("finished_at IS NULL OR finished_at >= coalesce(started_at, queued_at)",
                           name="ck_check_jobs_finished_at"),
        sa.CheckConstraint("status = 'FAILED' OR (error_code IS NULL AND error_message IS NULL)",
                           name="ck_check_jobs_errors"),
    )
    op.create_index("ix_check_jobs_org_status_queued", "document_check_jobs",
                    ["organization_id", "status", "queued_at", "id"])
    install_guards()


def downgrade() -> None:
    op.drop_table("document_check_jobs")
    op.drop_table("student_document_submissions")
    for name in ("pf_protect_student_original", "pf_validate_student_submission",
                 "pf_require_submission_job", "pf_protect_check_job_identity"):
        op.execute(f"DROP FUNCTION IF EXISTS {name}()")
    op.drop_constraint("uq_assignment_students_submission_target", "assignment_students", type_="unique")
    job_status.drop(op.get_bind(), checkfirst=True)
    # Keep append-only audit enum labels; PostgreSQL cannot remove individual values.
