"""Remove the retired student DOCX upload and check-assignment flow.

Drops ``student_document_submissions``, ``assignment_students``, and
``document_check_assignments`` along with their triggers/functions and enum,
removes ``document_check_jobs.submission_id``, and makes
``document_check_jobs.teacher_submission_id`` NOT NULL while keeping
``trg_protect_check_job_identity`` / ``pf_protect_check_job_identity`` active.
"""
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "9c1d2e3f4a5b"
down_revision = "9b0c1d2e3f4a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE document_check_findings DISABLE TRIGGER trg_validate_document_check_finding")
    op.execute("ALTER TABLE document_check_run_rules DISABLE TRIGGER trg_protect_run_rule")
    op.execute("ALTER TABLE document_check_jobs DISABLE TRIGGER trg_protect_check_job_identity")
    op.execute(
        "DELETE FROM document_check_findings "
        "WHERE job_id IN (SELECT id FROM document_check_jobs WHERE submission_id IS NOT NULL)"
    )
    op.execute(
        "DELETE FROM document_check_run_rules "
        "WHERE job_id IN (SELECT id FROM document_check_jobs WHERE submission_id IS NOT NULL)"
    )
    op.execute("DELETE FROM document_check_jobs WHERE submission_id IS NOT NULL")
    op.execute("ALTER TABLE document_check_jobs ENABLE TRIGGER trg_protect_check_job_identity")
    op.execute("ALTER TABLE document_check_run_rules ENABLE TRIGGER trg_protect_run_rule")
    op.execute("ALTER TABLE document_check_findings ENABLE TRIGGER trg_validate_document_check_finding")

    op.drop_constraint("ck_check_jobs_exactly_one_submission", "document_check_jobs", type_="check")
    op.drop_constraint("uq_check_jobs_submission", "document_check_jobs", type_="unique")
    op.drop_constraint("fk_check_jobs_submission_tenant", "document_check_jobs", type_="foreignkey")
    op.drop_column("document_check_jobs", "submission_id")
    op.alter_column(
        "document_check_jobs",
        "teacher_submission_id",
        existing_type=postgresql.UUID(),
        nullable=False,
    )

    op.execute("DROP TRIGGER IF EXISTS trg_require_submission_job ON student_document_submissions")
    op.execute("DROP TRIGGER IF EXISTS trg_validate_student_submission ON student_document_submissions")
    op.execute("DROP TRIGGER IF EXISTS trg_protect_student_original ON student_document_submissions")
    op.execute("DROP FUNCTION IF EXISTS pf_require_submission_job()")
    op.execute("DROP FUNCTION IF EXISTS pf_validate_student_submission()")
    op.execute("DROP FUNCTION IF EXISTS pf_protect_student_original()")

    op.execute("DROP TRIGGER IF EXISTS trg_validate_assignment_student ON assignment_students")
    op.execute("DROP FUNCTION IF EXISTS pf_validate_assignment_student()")
    op.execute("DROP TRIGGER IF EXISTS trg_protect_document_check_assignment_delete ON document_check_assignments")
    op.execute("DROP FUNCTION IF EXISTS pf_protect_document_check_assignment_delete()")
    op.execute("DROP TRIGGER IF EXISTS trg_validate_document_check_assignment ON document_check_assignments")
    op.execute("DROP FUNCTION IF EXISTS pf_validate_document_check_assignment()")

    op.drop_table("student_document_submissions")
    op.drop_table("assignment_students")
    op.drop_table("document_check_assignments")
    op.execute("DROP TYPE IF EXISTS document_check_assignment_status")


def downgrade() -> None:
    raise NotImplementedError(
        "Irreversible migration: the retired student DOCX upload tables "
        "(student_document_submissions, assignment_students, "
        "document_check_assignments) and document_check_jobs.submission_id "
        "were permanently removed. Restore from a database backup taken before "
        "this revision instead of downgrading."
    )
