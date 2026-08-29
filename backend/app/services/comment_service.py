"""Comment domain service (rule 3: dedicated service, not scattered across
endpoints). Anchor validity is deliberately recomputed against the report's
CURRENT document content (`report.document_data`) every time comments are
read - never stored - so a comment created against v1 correctly flips to
"invalid" the moment the student edits that exact sentence, and correctly
stays "valid" for everything the student didn't touch.
"""
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.documents.anchor import check_anchor
from app.documents.schemas import DocumentModel
from app.models.comment import Comment
from app.models.enums import AuditEventType, CommentStatus, ReportStatus
from app.permissions.rbac import require_student_owns_report, require_teacher_owns_group
from app.repositories.comment_repository import CommentRepository
from app.repositories.group_repository import GroupRepository
from app.repositories.internship_repository import InternshipRepository
from app.repositories.report_repository import ReportRepository
from app.services.audit_service import AuditService
from app.services.notification_service import NotificationService
from app.models.membership import OrganizationMembership
from app.models.student import Student
from sqlalchemy import select

# Comments may only be created/replied to while a review cycle is active -
# not on an untouched DRAFT, and not once the report is finalized.
REVIEWABLE_STATUSES = (ReportStatus.UNDER_REVIEW, ReportStatus.REVISION_REQUIRED)


class CommentService:
    def __init__(self, db: Session):
        self.db = db
        self.comment_repo = CommentRepository(db)
        self.report_repo = ReportRepository(db)
        self.internship_repo = InternshipRepository(db)
        self.group_repo = GroupRepository(db)
        self.audit = AuditService(db)
        self.notifications = NotificationService(db)

    def _notify_student(self, report, title: str, body: str) -> None:
        student_user_id = self.db.scalar(select(OrganizationMembership.user_id).join(Student).where(Student.id == report.student_id))
        if student_user_id:
            self.notifications.create(report.organization_id, student_user_id, "REPORT_COMMENT", title, body, f"/reports/{report.id}/edit")

    def _get_report_for_teacher(self, org_id: uuid.UUID, teacher_id: uuid.UUID, report_id: uuid.UUID):
        report = self.report_repo.get(org_id, report_id)
        if report is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
        internship = self.internship_repo.get(org_id, report.internship_id)
        require_teacher_owns_group(self.group_repo, org_id, teacher_id, internship.group_id)
        return report

    def _get_report_for_student(self, org_id: uuid.UUID, student_id: uuid.UUID, report_id: uuid.UUID):
        report = self.report_repo.get(org_id, report_id)
        if report is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
        require_student_owns_report(report.student_id, student_id)
        return report

    def _serialize_with_anchor_status(self, comment: Comment, document: DocumentModel | None) -> dict:
        anchor_status = None
        current_snippet = None
        if not comment.is_general and document is not None:
            result = check_anchor(document, comment.node_id, comment.start_offset, comment.end_offset, comment.text_snapshot)
            anchor_status = result.status
            current_snippet = result.current_text
        return {"comment": comment, "anchor_status": anchor_status, "current_node_text": current_snippet}

    def list_for_report(
        self, org_id: uuid.UUID, role: str, actor_teacher_id, actor_student_id,
        report_id: uuid.UUID, offset: int = 0, limit: int | None = None,
    ) -> list[dict]:
        if role == "TEACHER":
            report = self._get_report_for_teacher(org_id, actor_teacher_id, report_id)
        else:
            report = self._get_report_for_student(org_id, actor_student_id, report_id)

        document = DocumentModel.model_validate(report.document_data) if report.document_data else None
        roots = self.comment_repo.list_root_comments_for_report(org_id, report_id, offset, limit)
        return [self._serialize_with_anchor_status(c, document) for c in roots]

    def count_for_report(self, org_id: uuid.UUID, role: str, actor_teacher_id, actor_student_id, report_id: uuid.UUID) -> int:
        if role == "TEACHER":
            self._get_report_for_teacher(org_id, actor_teacher_id, report_id)
        else:
            self._get_report_for_student(org_id, actor_student_id, report_id)
        return self.comment_repo.count_root_comments_for_report(org_id, report_id)

    def create_inline_comment(
        self, org_id: uuid.UUID, teacher_id: uuid.UUID, actor_user_id: uuid.UUID, report_id: uuid.UUID,
        node_id: str, start_offset: int, end_offset: int, text_snapshot: str, body: str,
    ) -> Comment:
        report = self._get_report_for_teacher(org_id, teacher_id, report_id)
        if report.status not in REVIEWABLE_STATUSES:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Comments can only be added while a report is under review.")
        if report.current_version_id is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Report has no submitted version to comment on.")

        comment = Comment(
            organization_id=org_id, report_id=report.id, report_version_id=report.current_version_id,
            author_user_id=actor_user_id, is_general=False, node_id=node_id,
            start_offset=start_offset, end_offset=end_offset, text_snapshot=text_snapshot, body=body,
        )
        self.comment_repo.add(comment)
        self.audit.record(
            organization_id=org_id, actor_user_id=actor_user_id, event_type=AuditEventType.COMMENT_CREATED,
            entity_type="comment", entity_id=comment.id,
        )
        self._notify_student(report, "Новый комментарий к отчёту", body)
        self.db.commit()
        self.db.refresh(comment)
        return comment

    def create_general_comment(self, org_id: uuid.UUID, teacher_id: uuid.UUID, actor_user_id: uuid.UUID, report_id: uuid.UUID, body: str) -> Comment:
        report = self._get_report_for_teacher(org_id, teacher_id, report_id)
        if report.status not in REVIEWABLE_STATUSES:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Comments can only be added while a report is under review.")
        if report.current_version_id is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Report has no submitted version to comment on.")

        comment = Comment(
            organization_id=org_id, report_id=report.id, report_version_id=report.current_version_id,
            author_user_id=actor_user_id, is_general=True, body=body,
        )
        self.comment_repo.add(comment)
        self.audit.record(
            organization_id=org_id, actor_user_id=actor_user_id, event_type=AuditEventType.COMMENT_CREATED,
            entity_type="comment", entity_id=comment.id, metadata={"general": True},
        )
        self._notify_student(report, "Новый комментарий к отчёту", body)
        self.db.commit()
        self.db.refresh(comment)
        return comment

    def reply(self, org_id: uuid.UUID, role: str, actor_teacher_id, actor_student_id, actor_user_id: uuid.UUID, report_id: uuid.UUID, comment_id: uuid.UUID, body: str) -> Comment:
        if role == "TEACHER":
            report = self._get_report_for_teacher(org_id, actor_teacher_id, report_id)
        else:
            report = self._get_report_for_student(org_id, actor_student_id, report_id)

        if report.status not in REVIEWABLE_STATUSES:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This report is not currently under review.")

        parent = self.comment_repo.get(org_id, comment_id)
        if parent is None or parent.report_id != report.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")

        reply = Comment(
            organization_id=org_id, report_id=report.id, report_version_id=parent.report_version_id,
            author_user_id=actor_user_id, parent_comment_id=parent.id, is_general=parent.is_general,
            node_id=parent.node_id, start_offset=parent.start_offset, end_offset=parent.end_offset,
            text_snapshot=parent.text_snapshot, body=body,
        )
        self.comment_repo.add(reply)
        self.audit.record(
            organization_id=org_id, actor_user_id=actor_user_id, event_type=AuditEventType.COMMENT_REPLIED,
            entity_type="comment", entity_id=reply.id, metadata={"parent_comment_id": str(parent.id)},
        )
        if parent.author_user_id != actor_user_id:
            self.notifications.create(org_id, parent.author_user_id, "COMMENT_REPLY", "Получен ответ на комментарий", body, f"/reports/{report.id}/edit" if role == "STUDENT" else None)
        self.db.commit()
        self.db.refresh(reply)
        return reply

    def resolve(self, org_id: uuid.UUID, teacher_id: uuid.UUID, actor_user_id: uuid.UUID, report_id: uuid.UUID, comment_id: uuid.UUID) -> Comment:
        report = self._get_report_for_teacher(org_id, teacher_id, report_id)
        comment = self.comment_repo.get(org_id, comment_id)
        if comment is None or comment.report_id != report.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
        if comment.parent_comment_id is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only the root comment of a thread can be resolved.")

        comment.status = CommentStatus.RESOLVED
        comment.resolved_at = datetime.now(timezone.utc)
        comment.resolved_by_user_id = actor_user_id
        self.audit.record(
            organization_id=org_id, actor_user_id=actor_user_id, event_type=AuditEventType.COMMENT_RESOLVED,
            entity_type="comment", entity_id=comment.id,
        )
        self.db.commit()
        self.db.refresh(comment)
        return comment
