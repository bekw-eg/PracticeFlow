import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import AuditEventType


class AuditLog(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_org_entity_created_id", "organization_id", "entity_type", "entity_id", "created_at", "id"),
        Index("ix_audit_logs_org_sequence", "organization_id", "sequence", unique=True),
        Index("ix_audit_logs_org_action_created_id", "organization_id", "event_type", "created_at", "id"),
        Index("ix_audit_logs_org_actor_created_id", "organization_id", "actor_user_id", "created_at", "id"),
    )

    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[AuditEventType] = mapped_column(Enum(AuditEventType, name="audit_event_type"), nullable=False, index=True)
    entity_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    event_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Legacy entries deliberately remain nullable: their payload was not
    # signed at creation time and cannot honestly be made verifiable later.
    sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    previous_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_id_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    correlation_id_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    actor: Mapped["User | None"] = relationship(foreign_keys=[actor_user_id])
