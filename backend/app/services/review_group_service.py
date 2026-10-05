"""Server-scoped review folders and whole-group aggregation of pinned runs."""
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import and_, func, select

from app.models.document_check import DocumentCheckFinding, DocumentCheckJob, TeacherDocumentSubmission
from app.models.enums import AuditEventType, DocumentCheckJobStatus
from app.models.review_group import ReviewGroup, TeacherDocumentReview
from app.services.audit_service import AuditService
from app.services.teacher_document_submission_service import TeacherDocumentSubmissionService


class ReviewGroupService:
    def __init__(self, db):
        self.db = db

    def scope(self, ctx):
        teacher_id = TeacherDocumentSubmissionService._require_teacher(ctx)
        return select(ReviewGroup).where(ReviewGroup.organization_id == ctx.organization_id,
                                         ReviewGroup.teacher_id == teacher_id)

    def get(self, ctx, group_id):
        group = self.db.scalar(self.scope(ctx).where(ReviewGroup.id == group_id))
        if group is None:
            raise HTTPException(404, "Review group not found")
        return group

    def list(self, ctx, offset, limit):
        query = self.scope(ctx)
        total = self.db.scalar(select(func.count()).select_from(query.subquery()))
        return list(self.db.scalars(query.order_by(ReviewGroup.created_at.desc(), ReviewGroup.id.desc())
                                   .offset(offset).limit(limit))), total

    def create(self, ctx, request):
        teacher_id = TeacherDocumentSubmissionService._require_teacher(ctx)
        group = ReviewGroup(organization_id=ctx.organization_id, teacher_id=teacher_id, **request.model_dump())
        self.db.add(group)
        self.db.commit()
        self.db.refresh(group)
        return group

    def update(self, ctx, group_id, request):
        group = self.get(ctx, group_id)
        group.name, group.description = request.name, request.description
        self.db.commit()
        self.db.refresh(group)
        return group

    def works_query(self, ctx, group_id):
        group = self.get(ctx, group_id)
        return select(TeacherDocumentSubmission).where(
            TeacherDocumentSubmission.organization_id == group.organization_id,
            TeacherDocumentSubmission.teacher_id == group.teacher_id,
            TeacherDocumentSubmission.review_group_id == group.id,
        )

    def works(self, ctx, group_id, offset, limit, review_status=None):
        query = self.works_query(ctx, group_id)
        reviewed = TeacherDocumentSubmission.teacher_review.has(TeacherDocumentReview.completed_at.is_not(None))
        if review_status:
            query = query.where(reviewed if review_status == "completed" else ~reviewed)
        total = self.db.scalar(select(func.count()).select_from(query.subquery()))
        return list(self.db.scalars(query.order_by(TeacherDocumentSubmission.submitted_at.desc(),
                                                   TeacherDocumentSubmission.id.desc()).offset(offset).limit(limit))), total

    def summary(self, ctx, group_id):
        # Aggregate in SQL over ALL group works, independently of table pagination/filter.
        works = self.works_query(ctx, group_id).with_only_columns(TeacherDocumentSubmission.id).subquery()
        total = self.db.scalar(select(func.count()).select_from(works)) or 0
        reviewed = select(TeacherDocumentReview).join(works, works.c.id == TeacherDocumentReview.submission_id).where(
            TeacherDocumentReview.organization_id == ctx.organization_id,
            TeacherDocumentReview.completed_at.is_not(None),
        ).subquery()
        reviewed_count = self.db.scalar(select(func.count()).select_from(reviewed)) or 0
        included = select(DocumentCheckJob.id, DocumentCheckJob.teacher_submission_id, DocumentCheckJob.result_summary).join(
            reviewed, and_(reviewed.c.completed_job_id == DocumentCheckJob.id,
                           reviewed.c.submission_id == DocumentCheckJob.teacher_submission_id,
                           reviewed.c.organization_id == DocumentCheckJob.organization_id),
        ).where(DocumentCheckJob.status == DocumentCheckJobStatus.COMPLETED,
                DocumentCheckJob.result_summary.is_not(None)).subquery()
        included_count = self.db.scalar(select(func.count()).select_from(included)) or 0
        truncated = self.db.scalar(select(func.count()).select_from(included).where(
            included.c.result_summary["findings_truncated"].as_boolean().is_(True))) or 0
        counts = self.db.execute(select(
            DocumentCheckFinding.rule_type,
            func.count().label("violations_count"),
            func.count(func.distinct(included.c.teacher_submission_id)).label("works_count"),
        ).join(included, included.c.id == DocumentCheckFinding.job_id).where(
            DocumentCheckFinding.organization_id == ctx.organization_id,
        ).group_by(DocumentCheckFinding.rule_type).order_by(func.count().desc(), DocumentCheckFinding.rule_type)).all()
        return {"total_works": total, "pending_works": total - reviewed_count, "reviewed_works": reviewed_count,
                "included_works": included_count, "truncated_works": truncated,
                "violations": [dict(row._mapping) for row in counts]}


class TeacherReviewService:
    def __init__(self, db):
        self.db = db

    def save(self, ctx, submission_id, request, *, complete=False):
        submission = TeacherDocumentSubmissionService(self.db).get(ctx, submission_id)
        # Serialize first saves and completion, including requests in different API replicas.
        self.db.execute(select(TeacherDocumentSubmission.id).where(
            TeacherDocumentSubmission.organization_id == ctx.organization_id,
            TeacherDocumentSubmission.teacher_id == ctx.teacher_id,
            TeacherDocumentSubmission.id == submission.id,
        ).with_for_update()).scalar_one()
        review = self.db.scalar(select(TeacherDocumentReview).where(
            TeacherDocumentReview.organization_id == ctx.organization_id,
            TeacherDocumentReview.submission_id == submission.id,
        ).execution_options(populate_existing=True))
        if complete:
            job = self.db.scalar(select(DocumentCheckJob).where(
                DocumentCheckJob.organization_id == ctx.organization_id,
                DocumentCheckJob.teacher_submission_id == submission.id,
                DocumentCheckJob.id == request.job_id,
            ))
            if job is None:
                raise HTTPException(404, "Document check run not found")
            if job.status != DocumentCheckJobStatus.COMPLETED or job.result_summary is None:
                raise HTTPException(409, detail={"code": "REVIEW_RESULT_REQUIRED", "message": "A completed analysis is required."})
        if review and review.completed_at:
            if request.remarks == review.remarks and (not complete or request.job_id == review.completed_job_id):
                self.db.commit()
                return review
            raise HTTPException(409, detail={"code": "REVIEW_COMPLETED", "message": "This review is already completed."})
        if request.revision != (review.revision if review else 0):
            if review and not complete and request.remarks == review.remarks:
                self.db.commit()
                return review
            raise HTTPException(409, detail={"code": "REVIEW_CONFLICT", "message": "Review changed. Reload before saving."})
        if review is None:
            review = TeacherDocumentReview(organization_id=ctx.organization_id, submission_id=submission.id, revision=0)
            self.db.add(review)
        review.remarks = request.remarks
        review.revision += 1
        if complete:
            review.completed_job_id = job.id
            review.completed_by_teacher_id = ctx.teacher_id
            review.completed_at = datetime.now(UTC)
        AuditService(self.db).record(organization_id=ctx.organization_id, actor_user_id=ctx.user_id,
            event_type=AuditEventType.TEACHER_DOCUMENT_CHECK_MANAGED, entity_type="teacher_document_submission",
            entity_id=submission.id, metadata={"action": "COMPLETE_REVIEW" if complete else "SAVE_REVIEW"})
        self.db.commit()
        self.db.refresh(review)
        return review
