"""Tenant-scoped acceptance of immutable DOCX originals; no analyzer is run here."""
from __future__ import annotations

import re
import uuid
from contextlib import suppress
from datetime import UTC, datetime

from fastapi import HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.dependencies.auth import RequestContext
from app.core.config import settings
from app.models.document_check import (
    AssignmentStudent, DocumentCheckAssignment, DocumentCheckJob, StudentDocumentSubmission,
)
from app.models.enums import AuditEventType, DocumentCheckAssignmentStatus, DocumentCheckJobStatus, RoleName
from app.models.teacher_group import TeacherGroup
from app.permissions.rbac import require_role
from app.repositories.file_repository import FileRepository
from app.resource_protection import ResourceGuard
from app.services.audit_service import AuditService
from app.services.docx_preflight import stage_docx_upload
from app.services.submission_storage import build_submission_storage_key, persist_original
from app.storage import get_storage_service
from app.storage.base import StorageUnavailableError


def _missing() -> HTTPException:
    return HTTPException(status_code=404, detail="Document check object not found")


def _error(code: str, message: str, status_code: int = 409) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


class DocumentSubmissionService:
    def __init__(self, db: Session, resource_guard: ResourceGuard | None = None):
        self.db = db
        self.resource_guard = resource_guard
        self.storage = get_storage_service()
        self.audit = AuditService(db)

    def _student_assignments(self, ctx: RequestContext):
        require_role(ctx.role, RoleName.STUDENT)
        if not settings.DOCUMENT_CHECK_STUDENT_SUBMISSIONS_ENABLED:
            raise _missing()
        return select(DocumentCheckAssignment).join(
            AssignmentStudent,
            (AssignmentStudent.organization_id == DocumentCheckAssignment.organization_id)
            & (AssignmentStudent.assignment_id == DocumentCheckAssignment.id),
        ).where(
            DocumentCheckAssignment.organization_id == ctx.organization_id,
            AssignmentStudent.student_id == ctx.student_id,
            DocumentCheckAssignment.state.in_([
                DocumentCheckAssignmentStatus.PUBLISHED, DocumentCheckAssignmentStatus.CLOSED,
            ]),
        )

    def list_student_assignments(self, ctx: RequestContext, offset: int, limit: int):
        query = self._student_assignments(ctx)
        total = self.db.scalar(select(func.count()).select_from(query.subquery())) or 0
        items = list(self.db.scalars(query.order_by(
            DocumentCheckAssignment.created_at.desc(), DocumentCheckAssignment.id.desc(),
        ).offset(offset).limit(limit)))
        return items, total

    def student_assignment(
        self, ctx: RequestContext, assignment_id: uuid.UUID, *, include_draft: bool = False, lock: bool = False,
    ) -> tuple[DocumentCheckAssignment, AssignmentStudent]:
        require_role(ctx.role, RoleName.STUDENT)
        if not settings.DOCUMENT_CHECK_STUDENT_SUBMISSIONS_ENABLED:
            raise _missing()
        query = select(DocumentCheckAssignment).where(
            DocumentCheckAssignment.organization_id == ctx.organization_id,
            DocumentCheckAssignment.id == assignment_id,
        )
        if not include_draft:
            query = query.where(DocumentCheckAssignment.state != DocumentCheckAssignmentStatus.DRAFT)
        if lock:
            query = query.with_for_update(read=True).execution_options(populate_existing=True)
        assignment = self.db.scalar(query)
        if assignment is None:
            raise _missing()
        roster_query = select(AssignmentStudent).where(
            AssignmentStudent.organization_id == ctx.organization_id,
            AssignmentStudent.assignment_id == assignment_id,
            AssignmentStudent.student_id == ctx.student_id,
        )
        if lock:
            roster_query = roster_query.with_for_update()
        roster = self.db.scalar(roster_query)
        if roster is None:
            raise _missing()
        return assignment, roster

    def teacher_assignment(self, ctx: RequestContext, assignment_id: uuid.UUID) -> DocumentCheckAssignment:
        require_role(ctx.role, RoleName.TEACHER)
        assignment = self.db.scalar(select(DocumentCheckAssignment).join(
            TeacherGroup, TeacherGroup.group_id == DocumentCheckAssignment.group_id,
        ).where(
            DocumentCheckAssignment.organization_id == ctx.organization_id,
            DocumentCheckAssignment.id == assignment_id,
            TeacherGroup.teacher_id == ctx.teacher_id,
        ))
        if assignment is None:
            raise _missing()
        return assignment

    def list_submissions(
        self, ctx: RequestContext, assignment_id: uuid.UUID, offset: int, limit: int,
        student_id: uuid.UUID | None = None,
    ):
        require_role(ctx.role, RoleName.STUDENT, RoleName.TEACHER)
        if ctx.role == RoleName.STUDENT:
            self.student_assignment(ctx, assignment_id)
            student_id = ctx.student_id
        else:
            self.teacher_assignment(ctx, assignment_id)
            if student_id is not None and self.db.scalar(select(AssignmentStudent.id).where(
                AssignmentStudent.organization_id == ctx.organization_id,
                AssignmentStudent.assignment_id == assignment_id, AssignmentStudent.student_id == student_id,
            )) is None:
                raise _missing()
        query = select(StudentDocumentSubmission).where(
            StudentDocumentSubmission.organization_id == ctx.organization_id,
            StudentDocumentSubmission.assignment_id == assignment_id,
        )
        if student_id is not None:
            query = query.where(StudentDocumentSubmission.student_id == student_id)
        total = self.db.scalar(select(func.count()).select_from(query.subquery())) or 0
        items = list(self.db.scalars(query.order_by(
            StudentDocumentSubmission.submitted_at.desc(), StudentDocumentSubmission.id.desc(),
        ).offset(offset).limit(limit)))
        return items, total

    def _rejected(self, ctx: RequestContext, assignment_id: uuid.UUID, exc: HTTPException) -> None:
        code = exc.detail.get("code") if isinstance(exc.detail, dict) else None
        if code and code.startswith("DOCX_"):
            self.audit.record(
                organization_id=ctx.organization_id, actor_user_id=ctx.user_id,
                event_type=AuditEventType.DOCUMENT_SUBMISSION_REJECTED,
                entity_type="document_check_assignment", entity_id=assignment_id,
                metadata={"reason": code},
            )
            self.db.commit()

    def upload(
        self, ctx: RequestContext, assignment_id: uuid.UUID, upload: UploadFile, idempotency_key: str,
    ) -> tuple[StudentDocumentSubmission, bool]:
        self.student_assignment(ctx, assignment_id, include_draft=True)
        if not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", idempotency_key):
            raise _error("IDEMPOTENCY_KEY_INVALID", "Use an Idempotency-Key of 1–128 ASCII letters, digits, . _ : or -.", 400)
        if self.resource_guard is None:
            raise RuntimeError("A resource guard is required for uploads")
        self.resource_guard.check_upload_request(ctx.organization_id, ctx.user_id)

        # Validation is bounded and happens before object creation/quota reservation.
        try:
            with stage_docx_upload(upload) as validated:
                assignment, roster = self.student_assignment(ctx, assignment_id, include_draft=True, lock=True)
                previous = self.db.scalar(select(StudentDocumentSubmission).where(
                    StudentDocumentSubmission.organization_id == ctx.organization_id,
                    StudentDocumentSubmission.assignment_student_id == roster.id,
                    StudentDocumentSubmission.idempotency_key == idempotency_key,
                ))
                if previous is not None:
                    if (previous.sha256, previous.size_bytes, previous.original_filename) != (
                        validated.sha256, validated.size_bytes, validated.original_filename,
                    ):
                        raise _error("IDEMPOTENCY_KEY_CONFLICT", "This upload key was already used for a different file.")
                    # Release locks without changing the existing submission or job.
                    self.db.commit()
                    return previous, False
                if assignment.state != DocumentCheckAssignmentStatus.PUBLISHED:
                    code = ("DOCUMENT_CHECK_ASSIGNMENT_CLOSED" if assignment.state == DocumentCheckAssignmentStatus.CLOSED
                            else "DOCUMENT_CHECK_ASSIGNMENT_NOT_PUBLISHED")
                    raise _error(code, "This assignment is not open for submissions.")

                attempt_number = 1 + (self.db.scalar(select(func.max(StudentDocumentSubmission.attempt_number)).where(
                    StudentDocumentSubmission.organization_id == ctx.organization_id,
                    StudentDocumentSubmission.assignment_student_id == roster.id,
                )) or 0)
                reservation = self.resource_guard.reserve_upload(
                    ctx.organization_id, ctx.user_id, validated.size_bytes,
                    FileRepository(self.db).total_size_bytes(ctx.organization_id),
                )
                submission_id = uuid.uuid4()
                storage_key = build_submission_storage_key(
                    ctx.organization_id, assignment_id, ctx.student_id, submission_id, validated.sha256,
                )
                saved = False
                try:
                    persist_original(self.storage, storage_key, validated)
                    saved = True
                    now = datetime.now(UTC)
                    submission = StudentDocumentSubmission(
                        id=submission_id, organization_id=ctx.organization_id, assignment_id=assignment_id,
                        assignment_student_id=roster.id, student_id=ctx.student_id, attempt_number=attempt_number,
                        original_filename=validated.original_filename, storage_key=storage_key,
                        size_bytes=validated.size_bytes, sha256=validated.sha256, detected_mime=validated.content_type,
                        submitted_at=now, is_late=now > assignment.due_at, idempotency_key=idempotency_key,
                        preflight_schema_version=validated.preflight_version,
                    )
                    self.db.add(submission)
                    self.db.flush()
                    job = DocumentCheckJob(
                        organization_id=ctx.organization_id, submission_id=submission.id,
                        status=DocumentCheckJobStatus.QUEUED, queued_at=now,
                    )
                    self.db.add(job)
                    self.db.flush()
                    self.audit.record(
                        organization_id=ctx.organization_id, actor_user_id=ctx.user_id,
                        event_type=AuditEventType.DOCUMENT_SUBMISSION_UPLOADED,
                        entity_type="student_document_submission", entity_id=submission.id,
                        metadata={"attempt_number": attempt_number, "size_bytes": validated.size_bytes, "is_late": submission.is_late},
                    )
                    self.audit.record(
                        organization_id=ctx.organization_id, actor_user_id=ctx.user_id,
                        event_type=AuditEventType.DOCUMENT_CHECK_JOB_CREATED,
                        entity_type="document_check_job", entity_id=job.id, metadata={"status": "QUEUED"},
                    )
                    self.db.commit()
                except Exception as exc:
                    self.db.rollback()
                    if saved:
                        # A commit acknowledgement can be lost. Never delete an object
                        # unless a fresh connection proves it has no committed owner.
                        with suppress(Exception):
                            with Session(self.db.get_bind()) as verification:
                                persisted = verification.scalar(select(StudentDocumentSubmission.id).where(
                                    StudentDocumentSubmission.organization_id == ctx.organization_id,
                                    StudentDocumentSubmission.id == submission_id,
                                ))
                            if persisted is None:
                                self.storage.delete(storage_key)
                    with suppress(Exception):
                        self.resource_guard.cancel_upload(reservation)
                    if isinstance(exc, StorageUnavailableError):
                        raise _error("STORAGE_UNAVAILABLE", "File storage is temporarily unavailable. Please try again later.", 503) from None
                    raise _error("SUBMISSION_PERSISTENCE_UNAVAILABLE", "The submission could not be saved. Retry with the same upload key.", 503) from None

                with suppress(Exception):
                    self.resource_guard.complete_upload(reservation)
                # Loaded only after the successful commit; failures here must never
                # remove an accepted original. The upload key makes a retry safe.
                self.db.refresh(submission)
                return submission, True
        except HTTPException as exc:
            self.db.rollback()
            self._rejected(ctx, assignment_id, exc)
            raise

    def authorized_submission(
        self, ctx: RequestContext, submission_id: uuid.UUID,
    ) -> StudentDocumentSubmission:
        require_role(ctx.role, RoleName.STUDENT, RoleName.TEACHER)
        query = select(StudentDocumentSubmission).where(
            StudentDocumentSubmission.organization_id == ctx.organization_id,
            StudentDocumentSubmission.id == submission_id,
        )
        if ctx.role == RoleName.STUDENT:
            if not settings.DOCUMENT_CHECK_STUDENT_SUBMISSIONS_ENABLED:
                raise _missing()
            query = query.where(StudentDocumentSubmission.student_id == ctx.student_id)
        submission = self.db.scalar(query)
        if submission is None:
            raise _missing()
        if ctx.role == RoleName.TEACHER:
            self.teacher_assignment(ctx, submission.assignment_id)
        else:
            self.student_assignment(ctx, submission.assignment_id)
        return submission

    def download_original(self, ctx: RequestContext, submission_id: uuid.UUID):
        submission = self.authorized_submission(ctx, submission_id)
        try:
            stream = self.storage.open(submission.storage_key)
        except (StorageUnavailableError, FileNotFoundError):
            raise _error("STORAGE_UNAVAILABLE", "File storage is temporarily unavailable. Please try again later.", 503) from None
        try:
            self.audit.record(
                organization_id=ctx.organization_id, actor_user_id=ctx.user_id,
                event_type=(AuditEventType.DOCUMENT_SUBMISSION_STUDENT_DOWNLOADED if ctx.role == RoleName.STUDENT
                            else AuditEventType.DOCUMENT_SUBMISSION_TEACHER_DOWNLOADED),
                entity_type="student_document_submission", entity_id=submission.id,
                metadata={"size_bytes": submission.size_bytes},
            )
            self.db.commit()
            return submission, stream
        except Exception:
            stream.close()
            self.db.rollback()
            raise
