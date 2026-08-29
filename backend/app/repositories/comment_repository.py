import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.comment import Comment


class CommentRepository:
    """Comments are scoped transitively through Report.organization_id
    (Comment carries organization_id directly for query efficiency, but
    every write path derives it server-side from the report, never from
    client input — see CommentService)."""

    def __init__(self, db: Session):
        self.db = db

    def get(self, org_id: uuid.UUID, comment_id: uuid.UUID) -> Comment | None:
        stmt = select(Comment).where(Comment.id == comment_id, Comment.organization_id == org_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def list_root_comments_for_report(
        self, org_id: uuid.UUID, report_id: uuid.UUID, offset: int = 0, limit: int | None = None
    ) -> list[Comment]:
        """Top-level comments only (parent_comment_id IS NULL) — replies are
        loaded via the `replies` relationship, keeping the thread structure
        flat and simple per rule 9."""
        stmt = (
            select(Comment)
            .options(joinedload(Comment.author), joinedload(Comment.replies).joinedload(Comment.author))
            .where(Comment.organization_id == org_id, Comment.report_id == report_id, Comment.parent_comment_id.is_(None))
            .order_by(Comment.created_at, Comment.id)
        )
        stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.db.execute(stmt).unique().scalars().all())

    def count_root_comments_for_report(self, org_id: uuid.UUID, report_id: uuid.UUID) -> int:
        stmt = select(func.count()).select_from(Comment).where(
            Comment.organization_id == org_id,
            Comment.report_id == report_id,
            Comment.parent_comment_id.is_(None),
        )
        return int(self.db.scalar(stmt) or 0)

    def add(self, comment: Comment) -> Comment:
        self.db.add(comment)
        self.db.flush()
        return comment
