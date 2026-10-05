"""Teacher-only acceptance and access for immutable DOCX checks."""
from __future__ import annotations

import re
import uuid
from contextlib import suppress
from datetime import UTC, datetime

from fastapi import HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.dependencies.auth import RequestContext
from app.models.document_check import (
    CheckProfileVersion,
    CheckRule,
    TeacherDocumentLifecycle,
    TeacherDocumentSubmission,
)
from app.models.enums import (
    AuditEventType,
    CheckProfileVersionStatus,
    EXECUTABLE_CHECK_RULE_TYPES,
    RoleName,
)
from app.permissions.rbac import require_role
from app.repositories.file_repository import FileRepository
from app.resource_protection import ResourceGuard
from app.services.audit_service import AuditService
from app.services.docx_preflight import stage_docx_upload
from app.services.docx_html_preview import render_docx_html
from app.services.submission_storage import (
    build_teacher_submission_storage_key,
    persist_original,
)
from app.storage import get_storage_service
from app.storage.base import StorageUnavailableError


def _missing() -> HTTPException:
    return HTTPException(status_code=404, detail="Document check not found")


def _error(code: str, message: str, status_code: int = 409) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


class TeacherDocumentSubmissionService:
    def __init__(self, db: Session, resource_guard: ResourceGuard | None = None):
        self.db = db
        self.resource_guard = resource_guard
        self.storage = get_storage_service()
        self.audit = AuditService(db)

    @staticmethod
    def _require_teacher(ctx: RequestContext) -> uuid.UUID:
        require_role(ctx.role, RoleName.TEACHER)
        if ctx.teacher_id is None:
            raise _missing()
        return ctx.teacher_id

    def list(self, ctx: RequestContext, offset: int, limit: int, archived: bool = False):
        teacher_id = self._require_teacher(ctx)
        query = select(TeacherDocumentSubmission).where(
            TeacherDocumentSubmission.organization_id == ctx.organization_id,
            TeacherDocumentSubmission.teacher_id == teacher_id,
            TeacherDocumentSubmission.lifecycle.has(TeacherDocumentLifecycle.archived.is_(True))
            if archived else ~TeacherDocumentSubmission.lifecycle.has(TeacherDocumentLifecycle.archived.is_(True)),
        )
        total = self.db.scalar(select(func.count()).select_from(query.subquery())) or 0
        items = list(self.db.scalars(query.order_by(
            TeacherDocumentSubmission.submitted_at.desc(),
            TeacherDocumentSubmission.id.desc(),
        ).offset(offset).limit(limit)))
        return items, total

    def get(self, ctx: RequestContext, submission_id: uuid.UUID) -> TeacherDocumentSubmission:
        teacher_id = self._require_teacher(ctx)
        submission = self.db.scalar(select(TeacherDocumentSubmission).where(
            TeacherDocumentSubmission.organization_id == ctx.organization_id,
            TeacherDocumentSubmission.teacher_id == teacher_id,
            TeacherDocumentSubmission.id == submission_id,
        ))
        if submission is None:
            raise _missing()
        return submission

    def _published_version(self, ctx: RequestContext, profile_version_id: uuid.UUID) -> CheckProfileVersion:
        version = self.db.scalar(select(CheckProfileVersion).where(
            CheckProfileVersion.organization_id == ctx.organization_id,
            CheckProfileVersion.id == profile_version_id,
            CheckProfileVersion.state == CheckProfileVersionStatus.PUBLISHED,
        ))
        if version is None:
            raise _missing()
        executable_rule = self.db.scalar(select(CheckRule.id).where(
            CheckRule.organization_id == ctx.organization_id,
            CheckRule.profile_version_id == version.id,
            CheckRule.enabled.is_(True),
            CheckRule.rule_type.in_(EXECUTABLE_CHECK_RULE_TYPES),
        ).limit(1))
        if executable_rule is None:
            raise _error(
                "PROFILE_RULES_REQUIRED",
                "The selected profile has no enabled supported rules. Create and publish a new version with active rules.",
                422,
            )
        return version

    def _rejected(self, ctx: RequestContext, profile_version_id: uuid.UUID, exc: HTTPException) -> None:
        code = exc.detail.get("code") if isinstance(exc.detail, dict) else None
        if code and code.startswith("DOCX_"):
            self.audit.record(
                organization_id=ctx.organization_id,
                actor_user_id=ctx.user_id,
                event_type=AuditEventType.TEACHER_DOCUMENT_CHECK_REJECTED,
                entity_type="check_profile_version",
                entity_id=profile_version_id,
                metadata={"reason": code},
            )
            self.db.commit()

    def upload(
        self,
        ctx: RequestContext,
        profile_version_id: uuid.UUID,
        upload: UploadFile,
        idempotency_key: str,
        student_label: str | None,
        plagiarism_source_disclosure_allowed: bool = False,
        review_group_id: uuid.UUID | None = None,
        work_title: str | None = None,
        work_type: str | None = None,
    ) -> tuple[TeacherDocumentSubmission, bool]:
        teacher_id = self._require_teacher(ctx)
        self._published_version(ctx, profile_version_id)
        if review_group_id is not None:
            from app.services.review_group_service import ReviewGroupService
            ReviewGroupService(self.db).get(ctx, review_group_id)
        work_title = work_title.strip() if work_title else None
        if work_type not in (None, "COURSEWORK", "REPORT") or (work_title is not None and not 1 <= len(work_title) <= 255):
            raise _error("GROUP_WORK_METADATA_REQUIRED", "Invalid work title or type.", 422)
        if review_group_id and (not student_label or not student_label.strip() or not work_title or not work_type):
            raise _error("GROUP_WORK_METADATA_REQUIRED", "Student, title and work type are required for group works.", 422)
        if not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", idempotency_key):
            raise _error(
                "IDEMPOTENCY_KEY_INVALID",
                "Use an Idempotency-Key of 1–128 ASCII letters, digits, . _ : or -.",
                400,
            )
        normalized_label = student_label.strip() if student_label else None
        if normalized_label is not None and not 1 <= len(normalized_label) <= 255:
            raise _error("STUDENT_LABEL_INVALID", "Student label must contain 1–255 characters.", 400)
        if self.resource_guard is None:
            raise RuntimeError("A resource guard is required for uploads")
        self.resource_guard.check_upload_request(ctx.organization_id, ctx.user_id)

        try:
            with stage_docx_upload(upload) as validated:
                previous = self.db.scalar(select(TeacherDocumentSubmission).where(
                    TeacherDocumentSubmission.organization_id == ctx.organization_id,
                    TeacherDocumentSubmission.teacher_id == teacher_id,
                    TeacherDocumentSubmission.idempotency_key == idempotency_key,
                ))
                if previous is not None:
                    identity = (
                        previous.sha256,
                        previous.size_bytes,
                        previous.original_filename,
                        previous.profile_version_id,
                        previous.student_label,
                        previous.plagiarism_source_disclosure_allowed,
                        previous.review_group_id, previous.work_title, previous.work_type,
                    )
                    request_identity = (
                        validated.sha256,
                        validated.size_bytes,
                        validated.original_filename,
                        profile_version_id,
                        normalized_label,
                        plagiarism_source_disclosure_allowed,
                        review_group_id, work_title, work_type,
                    )
                    if identity != request_identity:
                        raise _error(
                            "IDEMPOTENCY_KEY_CONFLICT",
                            "This upload key was already used for another document check.",
                        )
                    self.db.commit()
                    return previous, False

                reservation = self.resource_guard.reserve_upload(
                    ctx.organization_id,
                    ctx.user_id,
                    validated.size_bytes,
                    FileRepository(self.db).total_size_bytes(ctx.organization_id),
                )
                submission_id = uuid.uuid4()
                storage_key = build_teacher_submission_storage_key(
                    ctx.organization_id, teacher_id, submission_id, validated.sha256,
                )
                saved = False
                try:
                    persist_original(self.storage, storage_key, validated)
                    saved = True
                    now = datetime.now(UTC)
                    submission = TeacherDocumentSubmission(
                        id=submission_id,
                        organization_id=ctx.organization_id,
                        teacher_id=teacher_id,
                        profile_version_id=profile_version_id,
                        student_label=normalized_label,
                        review_group_id=review_group_id, work_title=work_title, work_type=work_type,
                        original_filename=validated.original_filename,
                        storage_key=storage_key,
                        size_bytes=validated.size_bytes,
                        sha256=validated.sha256,
                        detected_mime=validated.content_type,
                        submitted_at=now,
                        idempotency_key=idempotency_key,
                        preflight_schema_version=validated.preflight_version,
                        plagiarism_source_disclosure_allowed=plagiarism_source_disclosure_allowed,
                    )
                    self.db.add(submission)
                    self.db.flush()
                    from app.services.document_settings_service import DocumentSettingsService
                    settings_service = DocumentSettingsService(self.db)
                    job = settings_service.create_job(submission, settings_service.ensure(submission))
                    self.audit.record(
                        organization_id=ctx.organization_id,
                        actor_user_id=ctx.user_id,
                        event_type=AuditEventType.TEACHER_DOCUMENT_CHECK_UPLOADED,
                        entity_type="teacher_document_submission",
                        entity_id=submission.id,
                        metadata={"size_bytes": validated.size_bytes},
                    )
                    self.audit.record(
                        organization_id=ctx.organization_id,
                        actor_user_id=ctx.user_id,
                        event_type=AuditEventType.DOCUMENT_CHECK_JOB_CREATED,
                        entity_type="document_check_job",
                        entity_id=job.id,
                        metadata={"status": "QUEUED", "source": "TEACHER_UPLOAD"},
                    )
                    self.db.commit()
                except Exception as exc:
                    self.db.rollback()
                    if saved:
                        with suppress(Exception):
                            with Session(self.db.get_bind()) as verification:
                                persisted = verification.scalar(select(TeacherDocumentSubmission.id).where(
                                    TeacherDocumentSubmission.organization_id == ctx.organization_id,
                                    TeacherDocumentSubmission.id == submission_id,
                                ))
                            if persisted is None:
                                self.storage.delete(storage_key)
                    with suppress(Exception):
                        self.resource_guard.cancel_upload(reservation)
                    if isinstance(exc, StorageUnavailableError):
                        raise _error(
                            "STORAGE_UNAVAILABLE",
                            "File storage is temporarily unavailable. Please try again later.",
                            503,
                        ) from None
                    raise _error(
                        "SUBMISSION_PERSISTENCE_UNAVAILABLE",
                        "The document check could not be saved. Retry with the same upload key.",
                        503,
                    ) from None

                with suppress(Exception):
                    self.resource_guard.complete_upload(reservation)
                self.db.refresh(submission)
                return submission, True
        except HTTPException as exc:
            self.db.rollback()
            self._rejected(ctx, profile_version_id, exc)
            raise

    def download_original(self, ctx: RequestContext, submission_id: uuid.UUID):
        submission = self.get(ctx, submission_id)
        from app.services.document_lifecycle_service import require_original
        require_original(submission)
        try:
            stream = self.storage.open(submission.storage_key)
        except (StorageUnavailableError, FileNotFoundError):
            raise _error(
                "STORAGE_UNAVAILABLE",
                "File storage is temporarily unavailable. Please try again later.",
                503,
            ) from None
        try:
            self.audit.record(
                organization_id=ctx.organization_id,
                actor_user_id=ctx.user_id,
                event_type=AuditEventType.TEACHER_DOCUMENT_CHECK_DOWNLOADED,
                entity_type="teacher_document_submission",
                entity_id=submission.id,
                metadata={"size_bytes": submission.size_bytes},
            )
            self.db.commit()
            return submission, stream
        except Exception:
            stream.close()
            self.db.rollback()
            raise

    def preview(self, ctx: RequestContext, submission_id: uuid.UUID):
        submission = self.get(ctx, submission_id)
        from app.services.document_lifecycle_service import require_original
        require_original(submission)
        try:
            stream = self.storage.open(submission.storage_key)
            try:
                return render_docx_html(stream)
            finally:
                stream.close()
        except (StorageUnavailableError, FileNotFoundError, OSError):
            raise _error(
                "PREVIEW_UNAVAILABLE",
                "The document preview is temporarily unavailable. Please try again later.",
                503,
            ) from None
        except Exception:
            raise _error("PREVIEW_INVALID", "The document could not be converted to a safe HTML preview.", 422) from None

    def paragraphs(self, submission, overrides=None):
        from app.services.document_paragraphs import inspect_paragraphs
        from app.services.document_lifecycle_service import require_original
        require_original(submission)
        try:
            stream = self.storage.open(submission.storage_key)
            try:
                return inspect_paragraphs(stream, overrides)
            finally:
                stream.close()
        except (StorageUnavailableError, FileNotFoundError, OSError):
            raise _error("PREVIEW_UNAVAILABLE", "The original document is temporarily unavailable.", 503) from None
        except Exception:
            raise _error("PREVIEW_INVALID", "Paragraph classification could not be read.", 422) from None
