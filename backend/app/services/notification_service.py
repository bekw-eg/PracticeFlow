import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.notification import Notification


class NotificationService:
    def __init__(self, db: Session):
        self.db = db

    def create(self, organization_id: uuid.UUID, user_id: uuid.UUID, type: str, title: str, body: str | None = None, link: str | None = None) -> Notification:
        item = Notification(organization_id=organization_id, user_id=user_id, type=type, title=title, body=body, link=link)
        self.db.add(item)
        self.db.flush()
        return item

    def list_for_user(
        self, organization_id: uuid.UUID, user_id: uuid.UUID, offset: int = 0, limit: int = 50
    ) -> list[Notification]:
        stmt = (
            select(Notification)
            .where(Notification.organization_id == organization_id, Notification.user_id == user_id)
            .order_by(Notification.created_at.desc(), Notification.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars().all())

    def count_for_user(self, organization_id: uuid.UUID, user_id: uuid.UUID) -> int:
        stmt = select(func.count()).select_from(Notification).where(
            Notification.organization_id == organization_id,
            Notification.user_id == user_id,
        )
        return int(self.db.scalar(stmt) or 0)

    def mark_read(self, organization_id: uuid.UUID, user_id: uuid.UUID, notification_id: uuid.UUID | None = None) -> None:
        if notification_id:
            item = self.db.scalar(select(Notification).where(Notification.id == notification_id, Notification.organization_id == organization_id, Notification.user_id == user_id))
            if item is None:
                return
            item.read_at = datetime.now(timezone.utc)
        else:
            items = self.db.execute(select(Notification).where(Notification.organization_id == organization_id, Notification.user_id == user_id, Notification.read_at.is_(None))).scalars()
            for item in items:
                item.read_at = datetime.now(timezone.utc)
        self.db.commit()
