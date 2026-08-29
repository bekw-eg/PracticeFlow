import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.enums import AuditEventType


class AuditEventOut(BaseModel):
    id: uuid.UUID
    timestamp: datetime
    action: AuditEventType
    actor_user_id: uuid.UUID | None
    target_type: str | None
    target_id: uuid.UUID | None
    metadata: dict | None
    request_id_hash: str | None
    correlation_id_hash: str | None
    sequence: int | None
    event_hash: str | None


class AuditIntegrityOut(BaseModel):
    valid: bool
    checked_events: int
    first_invalid_sequence: int | None = None
    retention_anchor_sequence: int = 0
