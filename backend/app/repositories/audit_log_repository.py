import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.audit_log import AuditLog


class AuditLogRepository:
    def __init__(self, db: Session):
        self.db = db

    def add(self, entry: AuditLog) -> AuditLog:
        self.db.add(entry)
        self.db.flush()
        return entry

    def list_for_entity(
        self, org_id: uuid.UUID, entity_type: str, entity_id: uuid.UUID, offset: int = 0, limit: int | None = None
    ) -> list[AuditLog]:
        stmt = (
            select(AuditLog)
            .options(joinedload(AuditLog.actor))
            .where(AuditLog.organization_id == org_id, AuditLog.entity_type == entity_type, AuditLog.entity_id == entity_id)
            .order_by(AuditLog.created_at, AuditLog.id)
        )
        stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.db.execute(stmt).scalars().all())

    def count_for_entity(self, org_id: uuid.UUID, entity_type: str, entity_id: uuid.UUID) -> int:
        stmt = select(func.count()).select_from(AuditLog).where(
            AuditLog.organization_id == org_id,
            AuditLog.entity_type == entity_type,
            AuditLog.entity_id == entity_id,
        )
        return int(self.db.scalar(stmt) or 0)
