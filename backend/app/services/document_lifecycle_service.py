"""Owner-only archival, disclosure and retryable original-object removal."""
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select

from app.models.document_check import DocumentCheckJob, TeacherDocumentLifecycle, TeacherDocumentSubmission
from app.models.enums import AuditEventType, DocumentCheckJobStatus
from app.services.audit_service import AuditService
from app.storage.base import StorageUnavailableError


def require_original(submission):
    if submission.lifecycle and submission.lifecycle.original_delete_requested_at:
        raise HTTPException(410, detail={"code": "DOCUMENT_ORIGINAL_DELETED", "message": "Original removed or pending removal."})


def source_disclosure_allowed(submission):
    state = submission.lifecycle
    if state:
        return not state.archived and not state.original_delete_requested_at and state.disclosure_allowed
    return submission.plagiarism_source_disclosure_allowed


class DocumentLifecycleService:
    def __init__(self, db, storage):
        self.db, self.storage = db, storage

    def _lock(self, submission):
        return self.db.scalar(select(TeacherDocumentSubmission).where(
            TeacherDocumentSubmission.organization_id == submission.organization_id,
            TeacherDocumentSubmission.id == submission.id,
        ).with_for_update().execution_options(populate_existing=True))

    def _state(self, submission, revision):
        state = submission.lifecycle
        if (state.revision if state else 0) != revision:
            raise HTTPException(409, detail={"code": "DOCUMENT_LIFECYCLE_CONFLICT", "message": "Document controls changed. Reload."})
        if state is None:
            state = TeacherDocumentLifecycle(
                organization_id=submission.organization_id, submission_id=submission.id,
                revision=1, archived=False,
                disclosure_allowed=submission.plagiarism_source_disclosure_allowed,
            )
            self.db.add(state)
            self.db.flush()
        else:
            state.revision += 1
        return state

    def _audit(self, ctx, submission, action):
        AuditService(self.db).record(
            organization_id=ctx.organization_id, actor_user_id=ctx.user_id,
            event_type=AuditEventType.TEACHER_DOCUMENT_CHECK_MANAGED,
            entity_type="teacher_document_submission", entity_id=submission.id,
            metadata={"action": action},
        )

    def update(self, ctx, submission, request):
        submission = self._lock(submission)
        state = self._state(submission, request.revision)
        state.archived = request.archived
        state.disclosure_allowed = request.disclosure_allowed
        self._audit(ctx, submission, "CONTROLS_UPDATED")
        self.db.commit()
        self.db.refresh(submission)
        return submission

    def delete_original(self, ctx, submission, revision):
        submission = self._lock(submission)
        state = submission.lifecycle
        if state and state.original_deleted_at:
            self.db.commit()
            return submission
        if self.db.scalar(select(DocumentCheckJob.id).where(
            DocumentCheckJob.organization_id == submission.organization_id,
            DocumentCheckJob.teacher_submission_id == submission.id,
            DocumentCheckJob.status.in_([DocumentCheckJobStatus.QUEUED, DocumentCheckJobStatus.PROCESSING]),
        ).limit(1)):
            raise HTTPException(409, detail={"code": "DOCUMENT_CHECK_ACTIVE", "message": "Wait for active checks to finish."})
        if state is None or state.original_delete_requested_at is None:
            state = self._state(submission, revision)
            state.original_delete_requested_at = datetime.now(UTC)
            state.disclosure_allowed = False
            self._audit(ctx, submission, "ORIGINAL_REMOVAL_REQUESTED")
        # Seal the request before touching storage. A crashed/failed request is
        # retryable; rechecks and reads already see 410, but quota is retained.
        self.db.commit()
        try:
            self.storage.delete(submission.storage_key)
        except (StorageUnavailableError, OSError):
            raise HTTPException(503, detail={"code": "DOCUMENT_REMOVAL_PENDING", "message": "Removal pending. Retry later."}) from None
        submission = self._lock(submission)
        state = submission.lifecycle
        if state.original_deleted_at is None:
            state.original_deleted_at = datetime.now(UTC)
            state.revision += 1
            self._audit(ctx, submission, "ORIGINAL_REMOVED")
        self.db.commit()
        self.db.refresh(submission)
        return submission
