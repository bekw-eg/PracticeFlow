"""Document-scoped drafts and append-only checks; global profiles are read-only here."""
from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import re
import uuid

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.document_check import CheckRule, DocumentCheckJob, DocumentCheckRunRule, DocumentCheckSettings
from app.models.enums import AuditEventType, DocumentCheckJobStatus
from app.schemas.document_check import CheckRuleWrite, DocumentSettingsWrite
from app.services.audit_service import AuditService


def _conflict(code, message):
    return HTTPException(status_code=409, detail={"code": code, "message": message})


def default_heading_level(level):
    return {"level": level, "allowed_fonts": ["Times New Roman"],
            "min_size_pt": 16 if level == 1 else 14, "max_size_pt": 16 if level == 1 else 14,
            "bold": True, "alignment": "CENTER", "line_spacing": 1.5,
            "space_before_pt": 0, "space_after_pt": 0, "first_line_indent_mm": 0,
            "left_indent_mm": 0, "right_indent_mm": 0}


class DocumentSettingsService:
    def __init__(self, db: Session):
        self.db = db

    def ensure(self, submission):
        key = (submission.organization_id, submission.id)
        existing = self.db.get(DocumentCheckSettings, key)
        if existing is not None:
            return existing
        profile_rules = list(self.db.scalars(select(CheckRule).where(
            CheckRule.organization_id == submission.organization_id,
            CheckRule.profile_version_id == submission.profile_version_id,
        ).order_by(CheckRule.sort_order)))
        rules = [CheckRuleWrite.model_validate({name: getattr(rule, name) for name in CheckRuleWrite.model_fields})
                 .model_dump(mode="json") for rule in profile_rules]
        headings = next((rule for rule in rules if rule["rule_type"] == "HEADINGS"), None)
        if headings is None:
            rules.append({"rule_type": "HEADINGS", "category": "headings", "severity": "ERROR",
                          "enabled": True, "sort_order": max((r["sort_order"] for r in rules), default=-1) + 1,
                          "config_schema_version": 1,
                          "config": {"levels": [default_heading_level(i) for i in range(1, 4)], "require_numbering": False}})
        else:
            present = {level["level"] for rule in rules if rule["rule_type"] == "HEADINGS" for level in rule["config"]["levels"]}
            headings["config"]["levels"].extend(default_heading_level(i) for i in range(1, 4) if i not in present)
        # Legacy documents initialize lazily from their pinned version; no old job
        # or published rule is rewritten. Concurrent first opens share one row.
        self.db.execute(insert(DocumentCheckSettings).values(
            organization_id=key[0], submission_id=key[1], revision=1,
            rules=rules, paragraph_overrides={},
        ).on_conflict_do_nothing(index_elements=["organization_id", "submission_id"]))
        return self.db.get(DocumentCheckSettings, key)

    def locked(self, submission):
        from app.models.document_check import TeacherDocumentSubmission
        from app.services.document_lifecycle_service import require_original
        submission = self.db.scalar(select(TeacherDocumentSubmission).where(
            TeacherDocumentSubmission.id == submission.id,
            TeacherDocumentSubmission.organization_id == submission.organization_id,
        ).with_for_update().execution_options(populate_existing=True))
        require_original(submission)
        self.ensure(submission)
        return self.db.scalar(select(DocumentCheckSettings).where(
            DocumentCheckSettings.organization_id == submission.organization_id,
            DocumentCheckSettings.submission_id == submission.id,
        ).with_for_update().execution_options(populate_existing=True))

    def save(self, submission, request: DocumentSettingsWrite):
        draft = self.locked(submission)
        rules = [rule.model_dump(mode="json") for rule in request.rules]
        if draft.revision != request.revision:
            # An uncertain network retry of the very same save is idempotent.
            if draft.rules == rules and draft.paragraph_overrides == request.paragraph_overrides:
                self.db.commit()
                return draft
            raise _conflict("DOCUMENT_SETTINGS_CONFLICT", "Settings changed in another tab. Reload the saved settings or keep your edits.")
        if draft.rules != rules or draft.paragraph_overrides != request.paragraph_overrides:
            draft.rules = deepcopy(rules)
            draft.paragraph_overrides = dict(request.paragraph_overrides)
            draft.revision += 1
        self.db.commit()
        self.db.refresh(draft)
        return draft

    def create_job(self, submission, draft, *, run_number=1, idempotency_key=None):
        snapshot_rules = [{**deepcopy(rule), "id": str(uuid.uuid4())} for rule in draft.rules]
        job = DocumentCheckJob(
            id=uuid.uuid4(), organization_id=submission.organization_id,
            teacher_submission_id=submission.id, submission_id=None,
            status=DocumentCheckJobStatus.QUEUED, queued_at=datetime.now(UTC), run_number=run_number,
            idempotency_key=idempotency_key,
            settings_snapshot={"schema_version": 1, "revision": draft.revision,
                               "paragraph_overrides": deepcopy(draft.paragraph_overrides), "rules": snapshot_rules},
        )
        self.db.add(job)
        self.db.flush()
        for rule in snapshot_rules:
            self.db.add(DocumentCheckRunRule(
                **{**rule, "id": uuid.UUID(rule["id"])},
                organization_id=submission.organization_id, job_id=job.id,
            ))
        self.db.flush()
        # A local similarity run is part of every immutable document-check
        # run.  It has its own result history but shares the durable worker
        # lease and retry lifecycle with the document-format analysis.
        from app.services.local_plagiarism_service import LocalPlagiarismService
        LocalPlagiarismService(self.db).queue_for_job(job, submission)
        return job

    def recheck(self, ctx, submission, revision: int, key: str):
        if not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", key):
            raise HTTPException(400, detail={"code": "IDEMPOTENCY_KEY_INVALID", "message": "Invalid recheck key."})
        draft = self.locked(submission)
        query = select(DocumentCheckJob).where(
            DocumentCheckJob.organization_id == submission.organization_id,
            DocumentCheckJob.teacher_submission_id == submission.id,
        )
        previous = self.db.scalar(query.where(DocumentCheckJob.idempotency_key == key))
        if previous is not None:
            if previous.settings_revision != revision:
                raise _conflict("IDEMPOTENCY_KEY_CONFLICT", "This key belongs to another settings revision.")
            self.db.commit()
            return previous
        if draft.revision != revision:
            raise _conflict("DOCUMENT_SETTINGS_CONFLICT", "Save or reload the latest document settings before checking.")
        # Each explicit request key owns one run, even after completion. A retry
        # with that key is handled above. Different requests get ordered runs.
        number = (self.db.scalar(select(func.max(DocumentCheckJob.run_number)).where(
            DocumentCheckJob.organization_id == submission.organization_id,
            DocumentCheckJob.teacher_submission_id == submission.id,
        )) or 0) + 1
        job = self.create_job(submission, draft, run_number=number, idempotency_key=key)
        AuditService(self.db).record(
            organization_id=ctx.organization_id, actor_user_id=ctx.user_id,
            event_type=AuditEventType.DOCUMENT_CHECK_JOB_CREATED, entity_type="document_check_job", entity_id=job.id,
            metadata={"status": "QUEUED", "source": "TEACHER_RECHECK"},
        )
        self.db.commit()
        self.db.refresh(job)
        return job

    def get_job(self, submission, job_id):
        job = self.db.scalar(select(DocumentCheckJob).where(
            DocumentCheckJob.organization_id == submission.organization_id,
            DocumentCheckJob.teacher_submission_id == submission.id, DocumentCheckJob.id == job_id,
        ))
        if job is None:
            raise HTTPException(404, detail="Document check run not found")
        return job

    def run_rules(self, submission, job):
        if job.settings_snapshot is not None:
            return job.settings_snapshot["rules"]
        # Historical runs keep their exact pinned global rules.
        return [{name: getattr(rule, name) for name in CheckRuleWrite.model_fields} for rule in self.db.scalars(
            select(CheckRule).where(CheckRule.organization_id == submission.organization_id,
                                    CheckRule.profile_version_id == submission.profile_version_id).order_by(CheckRule.sort_order))]
