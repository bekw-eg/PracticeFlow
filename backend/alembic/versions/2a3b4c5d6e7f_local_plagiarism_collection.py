"""Add organization-local exact-text similarity collection.

Revision ID: 2a3b4c5d6e7f
Revises: 1d5e6f7a8b9c
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg


revision = "2a3b4c5d6e7f"
down_revision = "1d5e6f7a8b9c"
branch_labels = None
depends_on = None


def _timestamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    for value in ("LOCAL_PLAGIARISM_RUN_COMPLETED", "LOCAL_PLAGIARISM_RUN_FAILED"):
        op.execute(f"ALTER TYPE audit_event_type ADD VALUE IF NOT EXISTS '{value}'")

    op.add_column(
        "teacher_document_submissions",
        sa.Column("plagiarism_source_disclosure_allowed", sa.Boolean(), server_default=sa.false(), nullable=False),
    )

    op.create_table(
        "local_plagiarism_indexes",
        sa.Column("organization_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("submission_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("algorithm_version", sa.String(80), nullable=False),
        sa.Column("eligible_word_count", sa.Integer(), nullable=False),
        sa.Column("excluded_word_count", sa.Integer(), nullable=False),
        sa.Column("paragraph_count", sa.Integer(), nullable=False),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["organization_id", "submission_id"],
            ["teacher_document_submissions.organization_id", "teacher_document_submissions.id"],
            name="fk_local_plagiarism_indexes_submission_tenant", ondelete="RESTRICT",
        ),
        sa.CheckConstraint("eligible_word_count >= 0", name="ck_local_plagiarism_indexes_eligible_words"),
        sa.CheckConstraint("excluded_word_count >= 0", name="ck_local_plagiarism_indexes_excluded_words"),
        sa.CheckConstraint("paragraph_count >= 0", name="ck_local_plagiarism_indexes_paragraph_count"),
        sa.CheckConstraint("length(algorithm_version) BETWEEN 1 AND 80", name="ck_local_plagiarism_indexes_algorithm"),
    )
    op.create_index(
        "ix_local_plagiarism_indexes_org_indexed", "local_plagiarism_indexes",
        ["organization_id", "indexed_at", "submission_id"],
    )

    op.create_table(
        "local_plagiarism_paragraphs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("submission_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("paragraph_index", sa.Integer(), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("word_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "submission_id"],
            ["local_plagiarism_indexes.organization_id", "local_plagiarism_indexes.submission_id"],
            name="fk_local_plagiarism_paragraphs_index", ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("organization_id", "submission_id", "paragraph_index", name="uq_local_plagiarism_paragraph_index"),
        sa.CheckConstraint("paragraph_index > 0", name="ck_local_plagiarism_paragraph_index_positive"),
        sa.CheckConstraint("word_count > 0", name="ck_local_plagiarism_paragraph_words_positive"),
        sa.CheckConstraint("length(normalized_text) > 0", name="ck_local_plagiarism_paragraph_text_nonempty"),
    )
    op.create_index(
        "ix_local_plagiarism_paragraphs_org_submission", "local_plagiarism_paragraphs",
        ["organization_id", "submission_id", "paragraph_index"],
    )

    op.create_table(
        "local_plagiarism_runs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("target_submission_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("status", pg.ENUM(name="document_check_job_status", create_type=False), nullable=False),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("algorithm_version", sa.String(80), nullable=False),
        sa.Column("minimum_match_words", sa.Integer(), nullable=False),
        sa.Column("target_word_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("excluded_word_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("matched_word_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("similarity_percent", sa.Numeric(5, 2), server_default="0", nullable=False),
        sa.Column("candidate_documents_available", sa.Integer(), server_default="0", nullable=False),
        sa.Column("candidate_documents_scanned", sa.Integer(), server_default="0", nullable=False),
        sa.Column("matches_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("matches_truncated", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("error_message", sa.String(500), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["organization_id", "job_id"], ["document_check_jobs.organization_id", "document_check_jobs.id"],
            name="fk_local_plagiarism_runs_job", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "target_submission_id"],
            ["teacher_document_submissions.organization_id", "teacher_document_submissions.id"],
            name="fk_local_plagiarism_runs_target", ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("organization_id", "id", name="uq_local_plagiarism_runs_org_id"),
        sa.UniqueConstraint("organization_id", "job_id", name="uq_local_plagiarism_runs_job"),
        sa.CheckConstraint("minimum_match_words >= 3", name="ck_local_plagiarism_runs_minimum_words"),
        sa.CheckConstraint("target_word_count >= 0", name="ck_local_plagiarism_runs_target_words"),
        sa.CheckConstraint("excluded_word_count >= 0", name="ck_local_plagiarism_runs_excluded_words"),
        sa.CheckConstraint("matched_word_count >= 0 AND matched_word_count <= target_word_count", name="ck_local_plagiarism_runs_matched_words"),
        sa.CheckConstraint("candidate_documents_available >= 0", name="ck_local_plagiarism_runs_candidate_available"),
        sa.CheckConstraint("candidate_documents_scanned >= 0 AND candidate_documents_scanned <= candidate_documents_available", name="ck_local_plagiarism_runs_candidate_scanned"),
        sa.CheckConstraint("matches_count >= 0", name="ck_local_plagiarism_runs_matches_count"),
        sa.CheckConstraint("similarity_percent >= 0 AND similarity_percent <= 100", name="ck_local_plagiarism_runs_percent"),
        sa.CheckConstraint(
            "(status = 'QUEUED' AND started_at IS NULL AND finished_at IS NULL) OR "
            "(status = 'PROCESSING' AND started_at IS NOT NULL AND finished_at IS NULL) OR "
            "(status = 'COMPLETED' AND started_at IS NOT NULL AND finished_at IS NOT NULL) OR "
            "(status = 'FAILED' AND finished_at IS NOT NULL)",
            name="ck_local_plagiarism_runs_status_timestamps",
        ),
    )
    op.create_index(
        "ix_local_plagiarism_runs_org_target", "local_plagiarism_runs",
        ["organization_id", "target_submission_id", "queued_at", "id"],
    )

    op.create_table(
        "local_plagiarism_matches",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("source_submission_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("target_paragraph_index", sa.Integer(), nullable=False),
        sa.Column("source_paragraph_index", sa.Integer(), nullable=False),
        sa.Column("matched_word_count", sa.Integer(), nullable=False),
        sa.Column("target_excerpt", sa.Text(), nullable=False),
        sa.Column("source_excerpt", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "run_id"], ["local_plagiarism_runs.organization_id", "local_plagiarism_runs.id"],
            name="fk_local_plagiarism_matches_run", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "source_submission_id"],
            ["teacher_document_submissions.organization_id", "teacher_document_submissions.id"],
            name="fk_local_plagiarism_matches_source", ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("organization_id", "run_id", "sequence", name="uq_local_plagiarism_matches_sequence"),
        sa.CheckConstraint("sequence > 0", name="ck_local_plagiarism_matches_sequence_positive"),
        sa.CheckConstraint("target_paragraph_index > 0", name="ck_local_plagiarism_matches_target_paragraph"),
        sa.CheckConstraint("source_paragraph_index > 0", name="ck_local_plagiarism_matches_source_paragraph"),
        sa.CheckConstraint("matched_word_count > 0", name="ck_local_plagiarism_matches_words_positive"),
        sa.CheckConstraint("length(target_excerpt) > 0", name="ck_local_plagiarism_matches_target_excerpt"),
        sa.CheckConstraint("length(source_excerpt) > 0", name="ck_local_plagiarism_matches_source_excerpt"),
    )
    op.create_index(
        "ix_local_plagiarism_matches_org_run_sequence", "local_plagiarism_matches",
        ["organization_id", "run_id", "sequence"],
    )


def downgrade() -> None:
    # The comparison index and excerpts are evidence retained with completed
    # results. Refuse a rollback that would silently erase them.
    op.execute("""
    DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM local_plagiarism_runs)
         OR EXISTS (SELECT 1 FROM local_plagiarism_indexes) THEN
        RAISE EXCEPTION 'Cannot downgrade with local plagiarism history; preserve data and roll forward';
      END IF;
    END $$;
    """)
    op.drop_index("ix_local_plagiarism_matches_org_run_sequence", table_name="local_plagiarism_matches")
    op.drop_table("local_plagiarism_matches")
    op.drop_index("ix_local_plagiarism_runs_org_target", table_name="local_plagiarism_runs")
    op.drop_table("local_plagiarism_runs")
    op.drop_index("ix_local_plagiarism_paragraphs_org_submission", table_name="local_plagiarism_paragraphs")
    op.drop_table("local_plagiarism_paragraphs")
    op.drop_index("ix_local_plagiarism_indexes_org_indexed", table_name="local_plagiarism_indexes")
    op.drop_table("local_plagiarism_indexes")
    op.drop_column("teacher_document_submissions", "plagiarism_source_disclosure_allowed")
    # PostgreSQL enum values remain so audit history remains readable.
