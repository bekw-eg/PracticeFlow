from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    event,
    inspect,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import (
    CheckProfileVersionStatus,
    CheckRuleSeverity,
    CheckRuleType,
    DocumentCheckJobStatus,
    EXECUTABLE_CHECK_RULE_TYPES,
)


class CheckProfile(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "check_profiles"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_check_profiles_org_id"),
        UniqueConstraint("organization_id", "name", name="uq_check_profiles_org_name"),
        Index("ix_check_profiles_org_created_id", "organization_id", "created_at", "id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    created_by_teacher_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teachers.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    versions: Mapped[list[CheckProfileVersion]] = relationship(
        back_populates="profile", order_by="CheckProfileVersion.version_number", cascade="all, delete-orphan"
    )


class CheckProfileVersion(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "check_profile_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "profile_id"],
            ["check_profiles.organization_id", "check_profiles.id"],
            name="fk_check_profile_versions_profile_tenant",
            ondelete="CASCADE",
        ),
        UniqueConstraint("organization_id", "id", name="uq_check_profile_versions_org_id"),
        UniqueConstraint(
            "organization_id", "profile_id", "version_number", name="uq_check_profile_versions_number"
        ),
        CheckConstraint("version_number > 0", name="ck_check_profile_versions_number_positive"),
        CheckConstraint(
            "(state = 'DRAFT' AND published_at IS NULL AND retired_at IS NULL) OR "
            "(state = 'PUBLISHED' AND published_at IS NOT NULL AND retired_at IS NULL) OR "
            "(state = 'RETIRED' AND published_at IS NOT NULL AND retired_at IS NOT NULL)",
            name="ck_check_profile_versions_state_timestamps",
        ),
        Index("ix_check_profile_versions_org_profile", "organization_id", "profile_id", "version_number"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[CheckProfileVersionStatus] = mapped_column(
        Enum(CheckProfileVersionStatus, name="check_profile_version_status"),
        nullable=False,
        default=CheckProfileVersionStatus.DRAFT,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    profile: Mapped[CheckProfile] = relationship(back_populates="versions")
    rules: Mapped[list[CheckRule]] = relationship(
        back_populates="profile_version", order_by="CheckRule.sort_order", cascade="all, delete-orphan"
    )

    @property
    def executable_rule_count(self) -> int:
        return sum(
            1 for rule in self.rules
            if rule.enabled and rule.rule_type in EXECUTABLE_CHECK_RULE_TYPES
        )


class CheckRule(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "check_rules"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "profile_version_id"],
            ["check_profile_versions.organization_id", "check_profile_versions.id"],
            name="fk_check_rules_version_tenant",
            ondelete="CASCADE",
        ),
        UniqueConstraint("organization_id", "id", name="uq_check_rules_org_id"),
        UniqueConstraint(
            "organization_id", "profile_version_id", "sort_order", name="uq_check_rules_version_sort"
        ),
        CheckConstraint("sort_order >= 0", name="ck_check_rules_sort_nonnegative"),
        CheckConstraint("config_schema_version = 1", name="ck_check_rules_schema_version"),
        CheckConstraint("jsonb_typeof(config) = 'object'", name="ck_check_rules_config_object"),
        Index("ix_check_rules_org_version_sort", "organization_id", "profile_version_id", "sort_order"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    profile_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    rule_type: Mapped[CheckRuleType] = mapped_column(Enum(CheckRuleType, name="check_rule_type"), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[CheckRuleSeverity] = mapped_column(
        Enum(CheckRuleSeverity, name="check_rule_severity"), nullable=False
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    config_schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False)

    profile_version: Mapped[CheckProfileVersion] = relationship(back_populates="rules")


class TeacherDocumentSubmission(UUIDPKMixin, TimestampMixin, Base):
    """An immutable DOCX uploaded directly by a Teacher for an ad-hoc check."""

    __tablename__ = "teacher_document_submissions"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id", "teacher_id", "review_group_id"],
                             ["review_groups.organization_id", "review_groups.teacher_id", "review_groups.id"],
                             ondelete="RESTRICT", name="fk_teacher_submission_review_group_owner"),
        CheckConstraint("work_type IS NULL OR work_type IN ('COURSEWORK', 'REPORT')", name="ck_teacher_submission_work_type"),
        CheckConstraint("review_group_id IS NULL OR (student_label IS NOT NULL AND work_title IS NOT NULL AND "
                        "length(btrim(work_title)) BETWEEN 1 AND 255 AND work_type IS NOT NULL)",
                        name="ck_teacher_submission_group_metadata"),
        Index("ix_teacher_submission_review_group", "organization_id", "teacher_id", "review_group_id", "submitted_at", "id"),
        ForeignKeyConstraint(
            ["organization_id", "profile_version_id"],
            ["check_profile_versions.organization_id", "check_profile_versions.id"],
            name="fk_teacher_submissions_version_tenant", ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "id", name="uq_teacher_submissions_org_id"),
        UniqueConstraint(
            "organization_id", "teacher_id", "idempotency_key",
            name="uq_teacher_submissions_idempotency",
        ),
        UniqueConstraint("storage_key", name="uq_teacher_submissions_storage_key"),
        CheckConstraint("size_bytes > 0", name="ck_teacher_submissions_size_positive"),
        CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="ck_teacher_submissions_sha256"),
        CheckConstraint("preflight_schema_version = 1", name="ck_teacher_submissions_preflight_version"),
        CheckConstraint(
            "length(idempotency_key) BETWEEN 1 AND 128",
            name="ck_teacher_submissions_idempotency_key",
        ),
        CheckConstraint(
            "student_label IS NULL OR length(btrim(student_label)) BETWEEN 1 AND 255",
            name="ck_teacher_submissions_student_label",
        ),
        CheckConstraint(
            "detected_mime = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'",
            name="ck_teacher_submissions_docx_mime",
        ),
        Index(
            "ix_teacher_submissions_org_teacher_submitted",
            "organization_id", "teacher_id", "submitted_at", "id",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    teacher_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teachers.id", ondelete="RESTRICT"), nullable=False
    )
    profile_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    student_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    review_group_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    work_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    work_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    detected_mime: Mapped[str] = mapped_column(String(100), nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    preflight_schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    # Every accepted direct submission joins the organization-local comparison
    # collection.  Sharing a source label and excerpt remains opt-in so an
    # unrelated Teacher never gets an implicit right to inspect another
    # Teacher's work.
    plagiarism_source_disclosure_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    profile_version: Mapped[CheckProfileVersion] = relationship()
    lifecycle: Mapped[TeacherDocumentLifecycle | None] = relationship(lazy="selectin", uselist=False)
    teacher_review: Mapped["TeacherDocumentReview | None"] = relationship(lazy="selectin", uselist=False, viewonly=True)
    jobs: Mapped[list[DocumentCheckJob]] = relationship(
        back_populates="teacher_submission", lazy="selectin",
        order_by="DocumentCheckJob.run_number.desc()",
    )
    plagiarism_index: Mapped[LocalPlagiarismIndex | None] = relationship(
        back_populates="submission", uselist=False
    )

    @property
    def job(self) -> DocumentCheckJob:
        return self.jobs[0]

    @property
    def latest_completed_job(self) -> DocumentCheckJob | None:
        return next((job for job in self.jobs if job.status == DocumentCheckJobStatus.COMPLETED), None)


class TeacherDocumentLifecycle(TimestampMixin, Base):
    """Mutable retention controls, separate from immutable submission evidence."""
    __tablename__ = "teacher_document_lifecycle"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id", "submission_id"],
                             ["teacher_document_submissions.organization_id", "teacher_document_submissions.id"],
                             ondelete="RESTRICT", name="fk_teacher_lifecycle_submission"),
        CheckConstraint("revision > 0", name="ck_teacher_lifecycle_revision"),
        CheckConstraint("original_deleted_at IS NULL OR original_delete_requested_at IS NOT NULL",
                        name="ck_teacher_lifecycle_deletion"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    submission_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    disclosure_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    original_delete_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    original_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DocumentCheckJob(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "document_check_jobs"
    __table_args__ = (
        UniqueConstraint("organization_id", "teacher_submission_id", "id", name="uq_check_jobs_exact_teacher_submission"),
        ForeignKeyConstraint(
            ["organization_id", "teacher_submission_id"],
            ["teacher_document_submissions.organization_id", "teacher_document_submissions.id"],
            name="fk_check_jobs_teacher_submission_tenant", ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "id", name="uq_check_jobs_org_id"),
        UniqueConstraint(
            "organization_id", "teacher_submission_id", "run_number", name="uq_check_jobs_teacher_run"
        ),
        UniqueConstraint("organization_id", "teacher_submission_id", "idempotency_key", name="uq_check_jobs_teacher_key"),
        CheckConstraint("run_number > 0", name="ck_check_jobs_run_positive"),
        CheckConstraint("settings_snapshot IS NULL OR jsonb_typeof(settings_snapshot) = 'object'", name="ck_check_jobs_snapshot_object"),
        CheckConstraint(
            "(status = 'QUEUED' AND started_at IS NULL AND finished_at IS NULL AND worker_id IS NULL AND lease_expires_at IS NULL) OR "
            "(status = 'PROCESSING' AND started_at IS NOT NULL AND finished_at IS NULL AND worker_id IS NOT NULL AND lease_expires_at IS NOT NULL) OR "
            "(status = 'COMPLETED' AND started_at IS NOT NULL AND finished_at IS NOT NULL AND worker_id IS NULL AND lease_expires_at IS NULL AND result_summary IS NOT NULL) OR "
            "(status = 'FAILED' AND finished_at IS NOT NULL AND worker_id IS NULL AND lease_expires_at IS NULL)",
            name="ck_check_jobs_status_timestamps",
        ),
        CheckConstraint("started_at IS NULL OR started_at >= queued_at", name="ck_check_jobs_started_at"),
        CheckConstraint("finished_at IS NULL OR finished_at >= coalesce(started_at, queued_at)",
                        name="ck_check_jobs_finished_at"),
        CheckConstraint("status = 'FAILED' OR (error_code IS NULL AND error_message IS NULL)",
                        name="ck_check_jobs_errors"),
        CheckConstraint("attempt_count >= 0", name="ck_check_jobs_attempt_count"),
        CheckConstraint("result_summary IS NULL OR jsonb_typeof(result_summary) = 'object'",
                        name="ck_check_jobs_result_summary"),
        Index("ix_check_jobs_org_status_queued", "organization_id", "status", "queued_at", "id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    teacher_submission_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[DocumentCheckJobStatus] = mapped_column(
        Enum(DocumentCheckJobStatus, name="document_check_job_status"),
        nullable=False, default=DocumentCheckJobStatus.QUEUED,
    )
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    analyzer_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    worker_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    run_number: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    settings_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    @property
    def settings_revision(self) -> int | None:
        return self.settings_snapshot.get("revision") if self.settings_snapshot else None

    teacher_submission: Mapped[TeacherDocumentSubmission] = relationship(
        back_populates="jobs", foreign_keys=[teacher_submission_id]
    )
    findings: Mapped[list[DocumentCheckFinding]] = relationship(
        back_populates="job", order_by="DocumentCheckFinding.sequence"
    )
    plagiarism_run: Mapped[LocalPlagiarismRun | None] = relationship(back_populates="job", uselist=False)


class LocalPlagiarismIndex(TimestampMixin, Base):
    """Private normalized paragraphs used only for organization-local matching."""

    __tablename__ = "local_plagiarism_indexes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "submission_id"],
            ["teacher_document_submissions.organization_id", "teacher_document_submissions.id"],
            name="fk_local_plagiarism_indexes_submission_tenant", ondelete="RESTRICT",
        ),
        CheckConstraint("eligible_word_count >= 0", name="ck_local_plagiarism_indexes_eligible_words"),
        CheckConstraint("excluded_word_count >= 0", name="ck_local_plagiarism_indexes_excluded_words"),
        CheckConstraint("paragraph_count >= 0", name="ck_local_plagiarism_indexes_paragraph_count"),
        CheckConstraint("length(algorithm_version) BETWEEN 1 AND 80", name="ck_local_plagiarism_indexes_algorithm"),
        Index("ix_local_plagiarism_indexes_org_indexed", "organization_id", "indexed_at", "submission_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    submission_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    algorithm_version: Mapped[str] = mapped_column(String(80), nullable=False)
    eligible_word_count: Mapped[int] = mapped_column(Integer, nullable=False)
    excluded_word_count: Mapped[int] = mapped_column(Integer, nullable=False)
    paragraph_count: Mapped[int] = mapped_column(Integer, nullable=False)
    indexed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    submission: Mapped[TeacherDocumentSubmission] = relationship(back_populates="plagiarism_index")
    paragraphs: Mapped[list[LocalPlagiarismParagraph]] = relationship(
        back_populates="index", order_by="LocalPlagiarismParagraph.paragraph_index", cascade="all, delete-orphan"
    )


class LocalPlagiarismParagraph(UUIDPKMixin, Base):
    __tablename__ = "local_plagiarism_paragraphs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "submission_id"],
            ["local_plagiarism_indexes.organization_id", "local_plagiarism_indexes.submission_id"],
            name="fk_local_plagiarism_paragraphs_index", ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "organization_id", "submission_id", "paragraph_index", name="uq_local_plagiarism_paragraph_index"
        ),
        CheckConstraint("paragraph_index > 0", name="ck_local_plagiarism_paragraph_index_positive"),
        CheckConstraint("word_count > 0", name="ck_local_plagiarism_paragraph_words_positive"),
        CheckConstraint("length(normalized_text) > 0", name="ck_local_plagiarism_paragraph_text_nonempty"),
        Index("ix_local_plagiarism_paragraphs_org_submission", "organization_id", "submission_id", "paragraph_index"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    submission_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    paragraph_index: Mapped[int] = mapped_column(Integer, nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False)

    index: Mapped[LocalPlagiarismIndex] = relationship(back_populates="paragraphs")


class LocalPlagiarismRun(UUIDPKMixin, TimestampMixin, Base):
    """One immutable local-similarity result for a document-check run."""

    __tablename__ = "local_plagiarism_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "job_id"],
            ["document_check_jobs.organization_id", "document_check_jobs.id"],
            name="fk_local_plagiarism_runs_job", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "target_submission_id"],
            ["teacher_document_submissions.organization_id", "teacher_document_submissions.id"],
            name="fk_local_plagiarism_runs_target", ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "id", name="uq_local_plagiarism_runs_org_id"),
        UniqueConstraint("organization_id", "job_id", name="uq_local_plagiarism_runs_job"),
        CheckConstraint("minimum_match_words >= 3", name="ck_local_plagiarism_runs_minimum_words"),
        CheckConstraint("target_word_count >= 0", name="ck_local_plagiarism_runs_target_words"),
        CheckConstraint("excluded_word_count >= 0", name="ck_local_plagiarism_runs_excluded_words"),
        CheckConstraint("matched_word_count >= 0 AND matched_word_count <= target_word_count", name="ck_local_plagiarism_runs_matched_words"),
        CheckConstraint("candidate_documents_available >= 0", name="ck_local_plagiarism_runs_candidate_available"),
        CheckConstraint("candidate_documents_scanned >= 0 AND candidate_documents_scanned <= candidate_documents_available", name="ck_local_plagiarism_runs_candidate_scanned"),
        CheckConstraint("matches_count >= 0", name="ck_local_plagiarism_runs_matches_count"),
        CheckConstraint("similarity_percent >= 0 AND similarity_percent <= 100", name="ck_local_plagiarism_runs_percent"),
        CheckConstraint(
            "(status = 'QUEUED' AND started_at IS NULL AND finished_at IS NULL) OR "
            "(status = 'PROCESSING' AND started_at IS NOT NULL AND finished_at IS NULL) OR "
            "(status = 'COMPLETED' AND started_at IS NOT NULL AND finished_at IS NOT NULL) OR "
            "(status = 'FAILED' AND finished_at IS NOT NULL)",
            name="ck_local_plagiarism_runs_status_timestamps",
        ),
        Index("ix_local_plagiarism_runs_org_target", "organization_id", "target_submission_id", "queued_at", "id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    target_submission_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[DocumentCheckJobStatus] = mapped_column(
        Enum(DocumentCheckJobStatus, name="document_check_job_status"), nullable=False,
        default=DocumentCheckJobStatus.QUEUED,
    )
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    algorithm_version: Mapped[str] = mapped_column(String(80), nullable=False)
    minimum_match_words: Mapped[int] = mapped_column(Integer, nullable=False)
    target_word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    excluded_word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    matched_word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    similarity_percent: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    candidate_documents_available: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    candidate_documents_scanned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    matches_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    matches_truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)

    job: Mapped[DocumentCheckJob] = relationship(back_populates="plagiarism_run")
    matches: Mapped[list[LocalPlagiarismMatch]] = relationship(
        back_populates="run", order_by="LocalPlagiarismMatch.sequence"
    )


class LocalPlagiarismMatch(UUIDPKMixin, Base):
    __tablename__ = "local_plagiarism_matches"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "run_id"],
            ["local_plagiarism_runs.organization_id", "local_plagiarism_runs.id"],
            name="fk_local_plagiarism_matches_run", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "source_submission_id"],
            ["teacher_document_submissions.organization_id", "teacher_document_submissions.id"],
            name="fk_local_plagiarism_matches_source", ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "run_id", "sequence", name="uq_local_plagiarism_matches_sequence"),
        CheckConstraint("sequence > 0", name="ck_local_plagiarism_matches_sequence_positive"),
        CheckConstraint("target_paragraph_index > 0", name="ck_local_plagiarism_matches_target_paragraph"),
        CheckConstraint("source_paragraph_index > 0", name="ck_local_plagiarism_matches_source_paragraph"),
        CheckConstraint("matched_word_count > 0", name="ck_local_plagiarism_matches_words_positive"),
        CheckConstraint("length(target_excerpt) > 0", name="ck_local_plagiarism_matches_target_excerpt"),
        CheckConstraint("length(source_excerpt) > 0", name="ck_local_plagiarism_matches_source_excerpt"),
        Index("ix_local_plagiarism_matches_org_run_sequence", "organization_id", "run_id", "sequence"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    source_submission_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    target_paragraph_index: Mapped[int] = mapped_column(Integer, nullable=False)
    source_paragraph_index: Mapped[int] = mapped_column(Integer, nullable=False)
    matched_word_count: Mapped[int] = mapped_column(Integer, nullable=False)
    target_excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    source_excerpt: Mapped[str] = mapped_column(Text, nullable=False)

    run: Mapped[LocalPlagiarismRun] = relationship(back_populates="matches")


class DocumentCheckSettings(TimestampMixin, Base):
    __tablename__ = "document_check_settings"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id", "submission_id"],
                             ["teacher_document_submissions.organization_id", "teacher_document_submissions.id"],
                             name="fk_document_settings_submission", ondelete="RESTRICT"),
        CheckConstraint("revision > 0", name="ck_document_settings_revision"),
        CheckConstraint("jsonb_typeof(rules) = 'array'", name="ck_document_settings_rules"),
        CheckConstraint("jsonb_typeof(paragraph_overrides) = 'object'", name="ck_document_settings_overrides"),
        CheckConstraint("jsonb_typeof(page_exclusions) = 'object'", name="ck_document_settings_page_exclusions"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    submission_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    rules: Mapped[list] = mapped_column(JSONB, nullable=False)
    paragraph_overrides: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    page_exclusions: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")


class DocumentCheckRunRule(UUIDPKMixin, TimestampMixin, Base):
    """Immutable executable rule identity owned by one run, never a global rule."""
    __tablename__ = "document_check_run_rules"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id", "job_id"],
                             ["document_check_jobs.organization_id", "document_check_jobs.id"],
                             name="fk_run_rules_job", ondelete="RESTRICT"),
        UniqueConstraint("organization_id", "job_id", "id", name="uq_run_rules_job_id"),
        UniqueConstraint("organization_id", "job_id", "sort_order", name="uq_run_rules_order"),
        CheckConstraint("jsonb_typeof(config) = 'object'", name="ck_run_rules_config"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    rule_type: Mapped[CheckRuleType] = mapped_column(Enum(CheckRuleType, name="check_rule_type"), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[CheckRuleSeverity] = mapped_column(Enum(CheckRuleSeverity, name="check_rule_severity"), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    config_schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False)


class DocumentCheckFinding(UUIDPKMixin, TimestampMixin, Base):
    """Structured analyzer output; it never stores text copied from the document."""

    __tablename__ = "document_check_findings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "job_id"],
            ["document_check_jobs.organization_id", "document_check_jobs.id"],
            name="fk_check_findings_job_tenant", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "check_rule_id"],
            ["check_rules.organization_id", "check_rules.id"],
            name="fk_check_findings_rule_tenant", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(["organization_id", "job_id", "run_rule_id"],
                             ["document_check_run_rules.organization_id", "document_check_run_rules.job_id", "document_check_run_rules.id"],
                             name="fk_check_findings_run_rule", ondelete="RESTRICT"),
        CheckConstraint("(check_rule_id IS NULL) <> (run_rule_id IS NULL)", name="ck_findings_rule_identity"),
        UniqueConstraint("organization_id", "id", name="uq_check_findings_org_id"),
        UniqueConstraint("organization_id", "job_id", "sequence", name="uq_check_findings_sequence"),
        CheckConstraint("sequence > 0", name="ck_check_findings_sequence_positive"),
        CheckConstraint("finding_schema_version = 1", name="ck_check_findings_schema_version"),
        CheckConstraint("jsonb_typeof(location) = 'object'", name="ck_check_findings_location_object"),
        CheckConstraint("jsonb_typeof(expected) = 'object'", name="ck_check_findings_expected_object"),
        CheckConstraint("jsonb_typeof(actual) = 'object'", name="ck_check_findings_actual_object"),
        Index("ix_check_findings_org_job_sequence", "organization_id", "job_id", "sequence"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    check_rule_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    run_rule_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    rule_type: Mapped[CheckRuleType] = mapped_column(Enum(CheckRuleType, name="check_rule_type"), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[CheckRuleSeverity] = mapped_column(Enum(CheckRuleSeverity, name="check_rule_severity"), nullable=False)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    property_name: Mapped[str] = mapped_column(String(80), nullable=False)
    location: Mapped[dict] = mapped_column(JSONB, nullable=False)
    expected: Mapped[dict] = mapped_column(JSONB, nullable=False)
    actual: Mapped[dict] = mapped_column(JSONB, nullable=False)
    finding_schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    job: Mapped[DocumentCheckJob] = relationship(back_populates="findings")


@event.listens_for(DocumentCheckFinding, "before_update")
@event.listens_for(DocumentCheckFinding, "before_delete")
@event.listens_for(DocumentCheckRunRule, "before_update")
@event.listens_for(DocumentCheckRunRule, "before_delete")
def _protect_document_check_finding(_mapper, _connection, _target) -> None:
    raise ValueError("Document check findings are immutable")


@event.listens_for(DocumentCheckJob, "before_update")
def _protect_check_job(_mapper, _connection, target) -> None:
    state = inspect(target)
    history = state.attrs.status.history
    previous = history.deleted[0] if history.deleted else target.status
    if previous in {DocumentCheckJobStatus.COMPLETED, DocumentCheckJobStatus.FAILED}:
        raise ValueError("Terminal check jobs are immutable")
    if any(state.attrs[key].history.has_changes() for key in (
        "organization_id", "teacher_submission_id", "run_number",
        "idempotency_key", "settings_snapshot", "queued_at",
    )):
        raise ValueError("Check job identity and settings snapshot are immutable")


@event.listens_for(DocumentCheckJob, "before_delete")
def _protect_check_job_delete(_mapper, _connection, _target) -> None:
    raise ValueError("Check jobs cannot be deleted")


@event.listens_for(TeacherDocumentSubmission, "before_update")
@event.listens_for(TeacherDocumentSubmission, "before_delete")
def _protect_teacher_original(_mapper, _connection, _target) -> None:
    raise ValueError("Teacher document submissions are immutable")


@event.listens_for(TeacherDocumentSubmission, "before_insert")
def _validate_teacher_submission(_mapper, connection: Connection, target: TeacherDocumentSubmission) -> None:
    _require_teacher_tenant(connection, target.teacher_id, target.organization_id)
    version_state = connection.scalar(
        select(CheckProfileVersion.state).where(
            CheckProfileVersion.id == target.profile_version_id,
            CheckProfileVersion.organization_id == target.organization_id,
        )
    )
    if version_state != CheckProfileVersionStatus.PUBLISHED:
        raise ValueError("Direct document checks require a published profile version")


def _require_teacher_tenant(connection: Connection, teacher_id: uuid.UUID, organization_id: uuid.UUID) -> None:
    from app.models.membership import OrganizationMembership
    from app.models.teacher import Teacher

    valid = connection.scalar(
        select(Teacher.id)
        .join(OrganizationMembership, Teacher.membership_id == OrganizationMembership.id)
        .where(Teacher.id == teacher_id, OrganizationMembership.organization_id == organization_id)
    )
    if valid is None:
        raise ValueError("Teacher and check profile must belong to the same organization")


@event.listens_for(CheckProfile, "before_insert")
@event.listens_for(CheckProfile, "before_update")
def _check_profile_tenant(_mapper, connection: Connection, target: CheckProfile) -> None:
    _require_teacher_tenant(connection, target.created_by_teacher_id, target.organization_id)


@event.listens_for(CheckProfileVersion, "before_update")
def _protect_published_version(_mapper, _connection: Connection, target: CheckProfileVersion) -> None:
    state_history = inspect(target).attrs.state.history
    previous = state_history.deleted[0] if state_history.deleted else target.state
    dirty_fields = {
        attr.key
        for attr in inspect(target).attrs
        if attr.history.has_changes() and attr.key not in {"state", "retired_at"}
    }
    if previous == CheckProfileVersionStatus.PUBLISHED and (
        target.state != CheckProfileVersionStatus.RETIRED or dirty_fields
    ):
        raise ValueError("Published profile versions are immutable")
    if previous == CheckProfileVersionStatus.RETIRED:
        raise ValueError("Retired profile versions are immutable")
    if previous == CheckProfileVersionStatus.DRAFT and target.state == CheckProfileVersionStatus.RETIRED:
        raise ValueError("A draft profile version cannot be retired")


@event.listens_for(CheckProfileVersion, "before_delete")
def _protect_published_version_delete(_mapper, _connection: Connection, target: CheckProfileVersion) -> None:
    if target.state != CheckProfileVersionStatus.DRAFT:
        raise ValueError("Published and retired profile versions are immutable")


@event.listens_for(CheckRule, "before_insert")
@event.listens_for(CheckRule, "before_update")
def _validate_rule(_mapper, connection: Connection, target: CheckRule) -> None:
    from app.schemas.document_check import validate_rule_config

    target.config = validate_rule_config(target.rule_type, target.config_schema_version, target.config)
    state = connection.scalar(
        select(CheckProfileVersion.state).where(
            CheckProfileVersion.id == target.profile_version_id,
            CheckProfileVersion.organization_id == target.organization_id,
        )
    )
    if state is not None and state != CheckProfileVersionStatus.DRAFT:
        raise ValueError("Rules of a published profile version are immutable")


@event.listens_for(CheckRule, "before_delete")
def _protect_rule_delete(_mapper, connection: Connection, target: CheckRule) -> None:
    state = connection.scalar(
        select(CheckProfileVersion.state).where(
            CheckProfileVersion.id == target.profile_version_id,
            CheckProfileVersion.organization_id == target.organization_id,
        )
    )
    if state != CheckProfileVersionStatus.DRAFT:
        raise ValueError("Rules of a published profile version are immutable")
