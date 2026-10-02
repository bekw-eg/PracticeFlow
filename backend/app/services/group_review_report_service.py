"""Pinned group evidence, explicit selections and private repeatable exports."""
import io
import math
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.document_check import DocumentCheckFinding, DocumentCheckJob, TeacherDocumentSubmission
from app.models.enums import AuditEventType, DocumentCheckJobStatus
from app.models.group_review_report import GroupReviewReport
from app.models.review_group import TeacherDocumentReview
from app.services.audit_service import AuditService
from app.services.review_group_service import ReviewGroupService
from app.storage import get_storage_service
from app.storage.base import StorageUnavailableError

PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


def _conflict(code):
    return HTTPException(409, detail={"code": code, "message": "Report state changed. Reload the saved report."})


def safe_finding(finding):
    """Allow structured measurements only. Unknown/free text is never copied.

    Font names can be user-controlled too, so only common known faces are
    copied; a withheld measurement is shown as unavailable, never invented.
    This is intentionally not an anonymizer for arbitrary teacher text.
    """
    allowed_strings = {"LEFT", "CENTER", "RIGHT", "JUSTIFY", "PORTRAIT", "LANDSCAPE", "UNKNOWN",
                       "A4", "LETTER", "LEGAL", "CUSTOM", "mm", "pt", "multiple", "auto", "exact", "atLeast",
                       "Arial", "Calibri", "Times New Roman", "Cambria", "Verdana", "Tahoma", "Aptos"}
    def scalar(value):
        if value is None or isinstance(value, bool):
            return value
        if isinstance(value, (float, int)) and math.isfinite(value) and abs(value) <= 1_000_000_000:
            return value
        if isinstance(value, str) and value in allowed_strings:
            return value
        return None
    def metric(value):
        result = {}
        for key in ("value", "unit", "min", "max", "width_mm", "height_mm", "name", "mode", "allowed"):
            if key not in value:
                continue
            result[key] = [scalar(item) for item in value[key]][:20] if isinstance(value[key], list) else scalar(value[key])
        return result
    location = {key: value for key, value in finding.location.items()
                if key in {"page", "paragraph_index", "run_index", "section_index", "table_index"}
                and type(value) is int and 0 < value <= 1_000_000}
    return {"id": str(finding.id), "rule_type": finding.rule_type.value, "location": location,
            "actual": metric(finding.actual), "expected": metric(finding.expected)}


class GroupReviewReportService:
    def __init__(self, db, storage=None):
        self.db = db
        self.storage = storage or get_storage_service()

    def scope(self, ctx, group_id):
        group = ReviewGroupService(self.db).get(ctx, group_id)
        return select(GroupReviewReport).where(GroupReviewReport.organization_id == group.organization_id,
            GroupReviewReport.teacher_id == group.teacher_id, GroupReviewReport.group_id == group.id)

    def get(self, ctx, group_id, report_id, *, lock=False):
        query = self.scope(ctx, group_id).where(GroupReviewReport.id == report_id)
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        report = self.db.scalar(query)
        if report is None:
            raise HTTPException(404, "Group report not found")
        return report

    def list(self, ctx, group_id, offset, limit):
        query = self.scope(ctx, group_id)
        total = self.db.scalar(select(func.count()).select_from(query.subquery()))
        reports = self.db.scalars(query.order_by(GroupReviewReport.created_at.desc(), GroupReviewReport.id.desc())
                                  .offset(offset).limit(limit))
        return [{"id": report.id, "locale": report.locale, "revision": report.revision,
                 "title": report.content["title"], "created_at": report.created_at, "generated_at": report.generated_at}
                for report in reports], total

    def _snapshot(self, ctx, group_id):
        # Independent repeatable-read transaction: summary, remarks and pinned
        # run IDs cannot straddle a concurrent upload/review completion.
        with Session(bind=self.db.get_bind().execution_options(isolation_level="REPEATABLE READ")) as read_db:
            groups = ReviewGroupService(read_db)
            group = groups.get(ctx, group_id)
            summary = groups.summary(ctx, group_id)
            if not summary["included_works"]:
                raise _conflict("GROUP_REPORT_NO_COMPLETED_REVIEWS")
            rows = read_db.execute(select(TeacherDocumentReview, DocumentCheckJob).join(
                TeacherDocumentSubmission, and_(TeacherDocumentSubmission.id == TeacherDocumentReview.submission_id,
                    TeacherDocumentSubmission.organization_id == TeacherDocumentReview.organization_id)).join(
                DocumentCheckJob, and_(DocumentCheckJob.id == TeacherDocumentReview.completed_job_id,
                    DocumentCheckJob.organization_id == TeacherDocumentReview.organization_id,
                    DocumentCheckJob.teacher_submission_id == TeacherDocumentReview.submission_id)).where(
                TeacherDocumentSubmission.review_group_id == group.id,
                TeacherDocumentSubmission.organization_id == ctx.organization_id,
                TeacherDocumentSubmission.teacher_id == ctx.teacher_id,
                TeacherDocumentReview.completed_at.is_not(None),
                TeacherDocumentReview.completed_by_teacher_id == ctx.teacher_id,
                DocumentCheckJob.status == DocumentCheckJobStatus.COMPLETED,
                DocumentCheckJob.result_summary.is_not(None),
            ).order_by(TeacherDocumentReview.submission_id)).all()
            return {"schema_version": 1, "group_name": group.name, "captured_at": datetime.now(UTC).isoformat(),
                "summary": {**summary, "violations": [{**row, "rule_type": row["rule_type"].value}
                                                       for row in summary["violations"]]},
                "runs": [{"submission_id": str(review.submission_id), "job_id": str(job.id)} for review, job in rows],
                "remarks": [{"submission_id": str(review.submission_id), "text": review.remarks}
                            for review, _ in rows if review.remarks.strip()],
                "skipped_works": sum(bool(job.result_summary.get("rules_skipped")) or
                                     job.result_summary.get("rules_evaluated") == 0 for _, job in rows),
                "unexecuted_works": sum(job.result_summary.get("rules_evaluated") == 0 for _, job in rows)}

    def create(self, ctx, group_id, request):
        query = self.scope(ctx, group_id).where(GroupReviewReport.request_id == request.request_id)
        existing = self.db.scalar(query)
        if existing:
            if existing.locale != request.locale:
                raise _conflict("GROUP_REPORT_REQUEST_CONFLICT")
            return existing
        snapshot = self._snapshot(ctx, group_id)
        from app.services.group_report_pptx import REPORT_TEXT
        report = GroupReviewReport(organization_id=ctx.organization_id, teacher_id=ctx.teacher_id,
            group_id=group_id, request_id=request.request_id, locale=request.locale, snapshot=snapshot,
            content={"title": REPORT_TEXT[request.locale]["default_title"].format(group=snapshot["group_name"]),
                "introduction": "", "conclusions": "", "selected_rule_types": [row["rule_type"] for row in snapshot["summary"]["violations"]],
                "finding_ids": [], "remark_submission_ids": [], "examples": [], "remarks": []})
        self.db.add(report)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            existing = self.db.scalar(query)
            if existing and existing.locale == request.locale:
                return existing
            raise _conflict("GROUP_REPORT_REQUEST_CONFLICT") from None
        self.db.refresh(report)
        return report

    def findings_query(self, ctx, report):
        # Validate every candidate against its tenant, owner, group, completed
        # review and exact captured job, never the submission's latest run.
        jobs = [uuid.UUID(run["job_id"]) for run in report.snapshot["runs"]]
        return select(DocumentCheckFinding).join(DocumentCheckJob, and_(
            DocumentCheckFinding.job_id == DocumentCheckJob.id,
            DocumentCheckFinding.organization_id == DocumentCheckJob.organization_id)).join(
            TeacherDocumentSubmission, and_(TeacherDocumentSubmission.id == DocumentCheckJob.teacher_submission_id,
                TeacherDocumentSubmission.organization_id == DocumentCheckJob.organization_id)).join(
            TeacherDocumentReview, and_(TeacherDocumentReview.submission_id == TeacherDocumentSubmission.id,
                TeacherDocumentReview.organization_id == TeacherDocumentSubmission.organization_id,
                TeacherDocumentReview.completed_job_id == DocumentCheckJob.id)).where(
            DocumentCheckFinding.organization_id == ctx.organization_id, DocumentCheckJob.id.in_(jobs),
            TeacherDocumentSubmission.teacher_id == ctx.teacher_id,
            TeacherDocumentSubmission.review_group_id == report.group_id,
            TeacherDocumentReview.completed_at.is_not(None), TeacherDocumentReview.completed_by_teacher_id == ctx.teacher_id,
            DocumentCheckJob.status == DocumentCheckJobStatus.COMPLETED)

    def findings(self, ctx, group_id, report_id, offset, limit, rule_type=None):
        report = self.get(ctx, group_id, report_id)
        query = self.findings_query(ctx, report)
        if rule_type:
            query = query.where(DocumentCheckFinding.rule_type == rule_type)
        total = self.db.scalar(select(func.count()).select_from(query.subquery()))
        items = self.db.scalars(query.order_by(DocumentCheckFinding.job_id, DocumentCheckFinding.sequence).offset(offset).limit(limit))
        return [safe_finding(item) for item in items], total

    def save(self, ctx, group_id, report_id, request):
        report = self.get(ctx, group_id, report_id, lock=True)
        if report.generated_at:
            raise _conflict("GROUP_REPORT_GENERATED")
        if request.revision != report.revision:
            raise _conflict("GROUP_REPORT_CONFLICT")
        if not request.title.strip():
            raise HTTPException(422, "Report title cannot be empty")
        types = list(dict.fromkeys(item.value for item in request.selected_rule_types))
        if not set(types) <= {row["rule_type"] for row in report.snapshot["summary"]["violations"]}:
            raise HTTPException(422, "Violation type is not in this snapshot")
        ids = list(dict.fromkeys(request.finding_ids))
        findings = list(self.db.scalars(self.findings_query(ctx, report).where(DocumentCheckFinding.id.in_(ids))))
        if len(findings) != len(ids):
            raise HTTPException(404, "Report finding not found")
        by_id = {finding.id: safe_finding(finding) for finding in findings}
        remarks = {item["submission_id"]: item["text"] for item in report.snapshot["remarks"]}
        remark_ids = list(dict.fromkeys(str(item) for item in request.remark_submission_ids))
        if not set(remark_ids) <= remarks.keys():
            raise HTTPException(404, "Report remark not found")
        # Authorization for remarks is checked through the same captured works.
        valid_submissions = set(self.db.scalars(select(TeacherDocumentSubmission.id).where(
            TeacherDocumentSubmission.organization_id == ctx.organization_id,
            TeacherDocumentSubmission.teacher_id == ctx.teacher_id,
            TeacherDocumentSubmission.review_group_id == group_id,
            TeacherDocumentSubmission.id.in_([uuid.UUID(item) for item in remark_ids]))))
        if len(valid_submissions) != len(remark_ids):
            raise HTTPException(404, "Report remark not found")
        report.content = {"title": request.title.strip(), "introduction": request.introduction,
            "conclusions": request.conclusions, "selected_rule_types": types, "finding_ids": [str(item) for item in ids],
            "remark_submission_ids": remark_ids, "examples": [by_id[item] for item in ids],
            "remarks": [remarks[item] for item in remark_ids]}
        report.revision += 1
        self.db.commit()
        self.db.refresh(report)
        return report

    def export(self, ctx, group_id, report_id, revision, guard):
        report = self.get(ctx, group_id, report_id, lock=True)
        if revision != report.revision:
            raise _conflict("GROUP_REPORT_CONFLICT")
        if report.generated_at:
            return report
        guard.check_export_rate(ctx.organization_id, ctx.user_id)
        lease = guard.acquire_export_slot(ctx.organization_id, ctx.user_id)
        key = f"orgs/{ctx.organization_id}/group-reports/{report.id}/{uuid.uuid4()}.pptx"
        stored = False
        try:
            from app.services.group_report_pptx import render_group_report
            data = render_group_report(report.snapshot, report.content, report.locale,
                                       timeout_seconds=guard.config.export_timeout_seconds)
            self.storage.save_new(key, io.BytesIO(data), PPTX_MIME)
            stored = True
            report.storage_key = key
            report.generated_at = datetime.now(UTC)
            AuditService(self.db).record(organization_id=ctx.organization_id, actor_user_id=ctx.user_id,
                event_type=AuditEventType.TEACHER_DOCUMENT_CHECK_MANAGED, entity_type="group_review_report",
                entity_id=report.id, metadata={"action": "GENERATE_PPTX", "revision": report.revision})
            self.db.commit()
            self.db.refresh(report)
            return report
        except StorageUnavailableError as exc:
            self.db.rollback()
            raise HTTPException(503, "Private presentation storage is temporarily unavailable") from exc
        except Exception:
            self.db.rollback()
            if stored:
                self.storage.delete(key)
            raise
        finally:
            guard.release_export(lease)
