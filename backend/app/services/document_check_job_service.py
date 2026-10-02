"""Durable PostgreSQL queue transitions for the independent DOCX analyzer."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document_check import (
    CheckRule, DocumentCheckAssignment, DocumentCheckFinding, DocumentCheckJob, DocumentCheckRunRule,
    StudentDocumentSubmission, TeacherDocumentSubmission,
)
from app.models.enums import AuditEventType, DocumentCheckJobStatus
from app.services.audit_service import AuditService
from app.services.document_analyzer import ANALYZER_VERSION, AnalyzerFinding, AnalyzerRule

SAFE_ERRORS = {
    "CHECK_STORAGE_UNAVAILABLE": "The original document is temporarily unavailable. Please try again later.",
    "CHECK_ORIGINAL_INTEGRITY": "The stored original did not pass its integrity check. Please contact support.",
    "CHECK_ANALYSIS_TIMEOUT": "The document check timed out. Please contact support.",
    "CHECK_ANALYSIS_FAILED": "The document could not be checked. Please contact support.",
    "CHECK_WORKER_STOPPED": "The document check was interrupted and could not be completed.",
}


class DocumentCheckJobService:
    def __init__(self, db: Session):
        self.db = db
        self.audit = AuditService(db)

    def claim_next(self, worker_id: str) -> DocumentCheckJob | None:
        job = self.db.scalar(
            select(DocumentCheckJob)
            .where(DocumentCheckJob.status == DocumentCheckJobStatus.QUEUED)
            .order_by(DocumentCheckJob.queued_at, DocumentCheckJob.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job is None:
            self.db.rollback()
            return None
        now = datetime.now(UTC)
        job.status = DocumentCheckJobStatus.PROCESSING
        job.started_at = now
        job.finished_at = None
        job.worker_id = worker_id[:128]
        job.lease_expires_at = now + timedelta(seconds=settings.DOCUMENT_CHECK_WORKER_LEASE_SECONDS)
        job.attempt_count += 1
        job.analyzer_version = ANALYZER_VERSION
        job.error_code = None
        job.error_message = None
        job.result_summary = None
        self.audit.record(
            organization_id=job.organization_id, actor_user_id=None,
            event_type=AuditEventType.DOCUMENT_CHECK_JOB_STARTED,
            entity_type="document_check_job", entity_id=job.id,
            metadata={"attempt_count": job.attempt_count, "analyzer_version": ANALYZER_VERSION.upper()},
        )
        self.db.commit()
        self.db.refresh(job)
        return job

    def lock_owned_job(self, job_id: uuid.UUID, worker_id: str) -> DocumentCheckJob | None:
        """Fence writes and heartbeats once a lease has expired or been reassigned."""
        return self.db.scalar(select(DocumentCheckJob).where(
            DocumentCheckJob.id == job_id,
            DocumentCheckJob.status == DocumentCheckJobStatus.PROCESSING,
            DocumentCheckJob.worker_id == worker_id[:128],
            DocumentCheckJob.lease_expires_at > datetime.now(UTC),
        ).with_for_update().execution_options(populate_existing=True))

    def heartbeat(self, job_id: uuid.UUID, worker_id: str) -> bool:
        job = self.lock_owned_job(job_id, worker_id)
        if job is None:
            self.db.rollback()
            return False
        job.lease_expires_at = datetime.now(UTC) + timedelta(seconds=settings.DOCUMENT_CHECK_WORKER_LEASE_SECONDS)
        self.db.commit()
        return True

    def payload(self, job_id: uuid.UUID, worker_id: str):
        job = self.db.scalar(select(DocumentCheckJob).where(
            DocumentCheckJob.id == job_id,
            DocumentCheckJob.status == DocumentCheckJobStatus.PROCESSING,
            DocumentCheckJob.worker_id == worker_id[:128],
        ))
        if job is None:
            return None
        if job.teacher_submission_id is not None:
            submission = self.db.scalar(select(TeacherDocumentSubmission).where(
                TeacherDocumentSubmission.organization_id == job.organization_id,
                TeacherDocumentSubmission.id == job.teacher_submission_id,
            ))
            if submission is None:
                return None
            profile_version_id = submission.profile_version_id
        else:
            submission = self.db.scalar(select(StudentDocumentSubmission).where(
                StudentDocumentSubmission.organization_id == job.organization_id,
                StudentDocumentSubmission.id == job.submission_id,
            ))
            if submission is None:
                return None
            assignment = self.db.scalar(select(DocumentCheckAssignment).where(
                DocumentCheckAssignment.organization_id == job.organization_id,
                DocumentCheckAssignment.id == submission.assignment_id,
            ))
            if assignment is None:
                return None
            profile_version_id = assignment.profile_version_id
        if job.settings_snapshot is not None:
            rules = list(self.db.scalars(select(DocumentCheckRunRule).where(
                DocumentCheckRunRule.organization_id == job.organization_id,
                DocumentCheckRunRule.job_id == job.id,
                DocumentCheckRunRule.enabled.is_(True),
            ).order_by(DocumentCheckRunRule.sort_order)))
            expected_rules = {item["id"]: item for item in job.settings_snapshot["rules"] if item["enabled"]}
            if len(rules) != len(expected_rules) or any(
                str(rule.id) not in expected_rules or rule.config != expected_rules[str(rule.id)]["config"] for rule in rules
            ):
                return None
        else:
            rules = list(self.db.scalars(select(CheckRule).where(
                CheckRule.organization_id == job.organization_id,
                CheckRule.profile_version_id == profile_version_id,
                CheckRule.enabled.is_(True),
            ).order_by(CheckRule.sort_order, CheckRule.id)))
        analyzer_rules = [AnalyzerRule(
            id=rule.id, rule_type=rule.rule_type, category=rule.category,
            severity=rule.severity, config=rule.config,
        ) for rule in rules]
        return submission, analyzer_rules

    def complete(
        self, job_id: uuid.UUID, worker_id: str, findings: list[AnalyzerFinding], summary: dict,
    ) -> bool:
        required_summary = {
            "analyzer_version", "rules_total", "rules_evaluated", "rules_skipped",
            "findings_count", "findings_truncated",
        }
        if not required_summary <= set(summary) or set(summary) - required_summary - {"first_page_exclusion"}:
            raise ValueError("Invalid analyzer result summary")
        counts = [summary[key] for key in ("rules_total", "rules_evaluated", "rules_skipped", "findings_count")]
        if (
            summary["analyzer_version"] != ANALYZER_VERSION
            or any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in counts)
            or summary["rules_total"] != summary["rules_evaluated"] + summary["rules_skipped"]
            or summary["findings_count"] != len(findings)
            or len(findings) > settings.DOCUMENT_CHECK_MAX_FINDINGS
            or not isinstance(summary["findings_truncated"], bool)
            or summary.get("first_page_exclusion") not in {None, "APPLIED", "BOUNDARY_UNKNOWN", "NO_CONTENT"}
            or (summary.get("first_page_exclusion") in {"BOUNDARY_UNKNOWN", "NO_CONTENT"}
                and (summary["rules_evaluated"] != 0 or summary["findings_count"] != 0))
        ):
            raise ValueError("Inconsistent analyzer result summary")
        job = self.db.scalar(select(DocumentCheckJob).where(
            DocumentCheckJob.id == job_id,
            DocumentCheckJob.status == DocumentCheckJobStatus.PROCESSING,
            DocumentCheckJob.worker_id == worker_id[:128],
        ).with_for_update())
        if job is None:
            self.db.rollback()
            return False
        if job.settings_snapshot is not None:
            identities = {uuid.UUID(rule["id"]): rule for rule in job.settings_snapshot["rules"] if rule["enabled"]}
        else:
            payload = self.payload(job_id, worker_id)
            identities = {rule.id: {"rule_type": rule.rule_type.value, "severity": rule.severity.value, "category": rule.category}
                          for rule in payload[1]} if payload else {}
        for sequence, finding in enumerate(findings, 1):
            identity = identities.get(finding.check_rule_id)
            if identity is None or (identity["rule_type"], identity["severity"], identity["category"]) != (
                finding.rule_type.value, finding.severity.value, finding.category,
            ):
                raise ValueError("Finding does not belong to an enabled rule of this run")
            self.db.add(DocumentCheckFinding(
                organization_id=job.organization_id, job_id=job.id,
                check_rule_id=finding.check_rule_id if job.settings_snapshot is None else None,
                run_rule_id=finding.check_rule_id if job.settings_snapshot is not None else None, sequence=sequence,
                rule_type=finding.rule_type, category=finding.category, severity=finding.severity,
                code=finding.code, property_name=finding.property_name,
                location=finding.location, expected=finding.expected, actual=finding.actual,
                finding_schema_version=1,
            ))
        # Findings may only be inserted while their job is PROCESSING. Flush
        # them before the same transaction makes the terminal status visible.
        self.db.flush()
        job.status = DocumentCheckJobStatus.COMPLETED
        job.finished_at = datetime.now(UTC)
        job.worker_id = None
        job.lease_expires_at = None
        job.result_summary = summary
        job.error_code = None
        job.error_message = None
        self.audit.record(
            organization_id=job.organization_id, actor_user_id=None,
            event_type=AuditEventType.DOCUMENT_CHECK_JOB_COMPLETED,
            entity_type="document_check_job", entity_id=job.id,
            metadata={
                "findings_count": summary["findings_count"],
                "rules_evaluated": summary["rules_evaluated"],
                "rules_skipped": summary["rules_skipped"],
                "findings_truncated": summary["findings_truncated"],
            },
        )
        self.db.commit()
        return True

    def retry_or_fail(self, job_id: uuid.UUID, worker_id: str, code: str) -> DocumentCheckJobStatus | None:
        if code not in SAFE_ERRORS:
            code = "CHECK_ANALYSIS_FAILED"
        job = self.db.scalar(select(DocumentCheckJob).where(
            DocumentCheckJob.id == job_id,
            DocumentCheckJob.status == DocumentCheckJobStatus.PROCESSING,
            DocumentCheckJob.worker_id == worker_id[:128],
        ).with_for_update())
        if job is None:
            self.db.rollback()
            return None
        job.worker_id = None
        job.lease_expires_at = None
        if job.attempt_count < settings.DOCUMENT_CHECK_WORKER_MAX_ATTEMPTS:
            job.status = DocumentCheckJobStatus.QUEUED
            job.started_at = None
            job.finished_at = None
            job.analyzer_version = None
            job.error_code = None
            job.error_message = None
            job.result_summary = None
        else:
            job.status = DocumentCheckJobStatus.FAILED
            job.finished_at = datetime.now(UTC)
            job.error_code = code
            job.error_message = SAFE_ERRORS[code]
            self.audit.record(
                organization_id=job.organization_id, actor_user_id=None,
                event_type=AuditEventType.DOCUMENT_CHECK_JOB_FAILED,
                entity_type="document_check_job", entity_id=job.id,
                metadata={"error_code": code, "attempt_count": job.attempt_count},
            )
        from app.services.local_plagiarism_service import LocalPlagiarismService
        LocalPlagiarismService(self.db).retry_or_fail_with_job(job)
        self.db.commit()
        return job.status

    def recover_stale(self) -> int:
        recovered = 0
        while recovered < 100:
            now = datetime.now(UTC)
            job = self.db.scalar(select(DocumentCheckJob).where(
                DocumentCheckJob.status == DocumentCheckJobStatus.PROCESSING,
                DocumentCheckJob.lease_expires_at < now,
            ).order_by(DocumentCheckJob.lease_expires_at).with_for_update(skip_locked=True).limit(1))
            if job is None:
                self.db.rollback()
                break
            job.worker_id = None
            job.lease_expires_at = None
            if job.attempt_count < settings.DOCUMENT_CHECK_WORKER_MAX_ATTEMPTS:
                job.status = DocumentCheckJobStatus.QUEUED
                job.started_at = None
                job.finished_at = None
                job.analyzer_version = None
                job.error_code = None
                job.error_message = None
                job.result_summary = None
            else:
                job.status = DocumentCheckJobStatus.FAILED
                job.finished_at = now
                job.error_code = "CHECK_WORKER_STOPPED"
                job.error_message = SAFE_ERRORS["CHECK_WORKER_STOPPED"]
                self.audit.record(
                    organization_id=job.organization_id, actor_user_id=None,
                    event_type=AuditEventType.DOCUMENT_CHECK_JOB_FAILED,
                    entity_type="document_check_job", entity_id=job.id,
                    metadata={"error_code": "CHECK_WORKER_STOPPED", "attempt_count": job.attempt_count},
                )
            from app.services.local_plagiarism_service import LocalPlagiarismService
            LocalPlagiarismService(self.db).retry_or_fail_with_job(job)
            self.db.commit()
            recovered += 1
        return recovered

    def list_findings(self, job: DocumentCheckJob, offset: int, limit: int):
        query = select(DocumentCheckFinding).where(
            DocumentCheckFinding.organization_id == job.organization_id,
            DocumentCheckFinding.job_id == job.id,
        )
        from sqlalchemy import func
        total = self.db.scalar(select(func.count()).select_from(query.subquery())) or 0
        items = list(self.db.scalars(query.order_by(DocumentCheckFinding.sequence).offset(offset).limit(limit)))
        return items, total
