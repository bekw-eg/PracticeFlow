"""Teacher review groups and reviews pinned to an exact completed analysis."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "4c5d6e7f8091"
down_revision = "3b4c5d6e7f80"
branch_labels = None
depends_on = None


def install_review_guards():
    op.execute("""
    CREATE OR REPLACE FUNCTION pf_protect_teacher_review() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP <> 'INSERT' THEN
        IF OLD.completed_at IS NOT NULL THEN
          RAISE EXCEPTION 'Completed teacher reviews are immutable';
        END IF;
        IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
        IF (OLD.organization_id, OLD.submission_id) IS DISTINCT FROM (NEW.organization_id, NEW.submission_id) THEN
          RAISE EXCEPTION 'Teacher review identity is immutable';
        END IF;
      END IF;
      IF NEW.completed_at IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM document_check_jobs j JOIN teacher_document_submissions s
          ON s.organization_id = j.organization_id AND s.id = j.teacher_submission_id
        WHERE j.organization_id = NEW.organization_id AND j.id = NEW.completed_job_id
          AND s.id = NEW.submission_id AND s.teacher_id = NEW.completed_by_teacher_id
          AND j.status = 'COMPLETED' AND j.result_summary IS NOT NULL
      ) THEN RAISE EXCEPTION 'Review requires an owned completed analysis'; END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER trg_protect_teacher_review BEFORE INSERT OR UPDATE OR DELETE ON teacher_document_reviews
      FOR EACH ROW EXECUTE FUNCTION pf_protect_teacher_review();
    """)


def upgrade():
    op.create_table("review_groups",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("teacher_id", pg.UUID(as_uuid=True), sa.ForeignKey("teachers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("organization_id", "teacher_id", "id", name="uq_review_groups_owner"),
        sa.CheckConstraint("length(btrim(name)) BETWEEN 1 AND 255", name="ck_review_groups_name"),
    )
    op.create_index("ix_review_groups_owner_created", "review_groups", ["organization_id", "teacher_id", "created_at", "id"])
    op.add_column("teacher_document_submissions", sa.Column("review_group_id", pg.UUID(as_uuid=True)))
    op.add_column("teacher_document_submissions", sa.Column("work_title", sa.String(255)))
    op.add_column("teacher_document_submissions", sa.Column("work_type", sa.String(20)))
    op.create_foreign_key("fk_teacher_submission_review_group_owner", "teacher_document_submissions", "review_groups",
                          ["organization_id", "teacher_id", "review_group_id"], ["organization_id", "teacher_id", "id"], ondelete="RESTRICT")
    op.create_check_constraint("ck_teacher_submission_work_type", "teacher_document_submissions",
                               "work_type IS NULL OR work_type IN ('COURSEWORK', 'REPORT')")
    op.create_check_constraint("ck_teacher_submission_group_metadata", "teacher_document_submissions",
        "review_group_id IS NULL OR (student_label IS NOT NULL AND work_title IS NOT NULL AND "
        "length(btrim(work_title)) BETWEEN 1 AND 255 AND work_type IS NOT NULL)")
    op.create_index("ix_teacher_submission_review_group", "teacher_document_submissions",
                     ["organization_id", "teacher_id", "review_group_id", "submitted_at", "id"])
    op.create_unique_constraint("uq_check_jobs_exact_teacher_submission", "document_check_jobs",
                                ["organization_id", "teacher_submission_id", "id"])
    op.create_table("teacher_document_reviews",
        sa.Column("organization_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("submission_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("remarks", sa.Text(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("completed_by_teacher_id", pg.UUID(as_uuid=True), sa.ForeignKey("teachers.id", ondelete="RESTRICT")),
        sa.Column("completed_job_id", pg.UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id", "submission_id"],
                                ["teacher_document_submissions.organization_id", "teacher_document_submissions.id"],
                                ondelete="RESTRICT", name="fk_teacher_review_submission"),
        sa.ForeignKeyConstraint(["organization_id", "submission_id", "completed_job_id"],
                                ["document_check_jobs.organization_id", "document_check_jobs.teacher_submission_id", "document_check_jobs.id"],
                                ondelete="RESTRICT", name="fk_teacher_review_exact_job"),
        sa.CheckConstraint("revision > 0", name="ck_teacher_review_revision"),
        sa.CheckConstraint("length(remarks) <= 10000", name="ck_teacher_review_remarks"),
        sa.CheckConstraint("(completed_at IS NULL AND completed_by_teacher_id IS NULL AND completed_job_id IS NULL) OR "
                           "(completed_at IS NOT NULL AND completed_by_teacher_id IS NOT NULL AND completed_job_id IS NOT NULL)",
                           name="ck_teacher_review_completion"),
    )
    install_review_guards()


def downgrade():
    op.execute("DROP FUNCTION IF EXISTS pf_protect_teacher_review() CASCADE")
    op.drop_table("teacher_document_reviews")
    op.drop_constraint("uq_check_jobs_exact_teacher_submission", "document_check_jobs")
    op.drop_index("ix_teacher_submission_review_group", table_name="teacher_document_submissions")
    op.drop_constraint("ck_teacher_submission_group_metadata", "teacher_document_submissions")
    op.drop_constraint("ck_teacher_submission_work_type", "teacher_document_submissions")
    op.drop_constraint("fk_teacher_submission_review_group_owner", "teacher_document_submissions")
    for column in ("work_type", "work_title", "review_group_id"):
        op.drop_column("teacher_document_submissions", column)
    op.drop_table("review_groups")
