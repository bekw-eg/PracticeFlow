"""Append-only tenant audit logging with verifiable per-tenant hash chains."""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.audit_context import fingerprint, get_audit_context
from app.models.audit_chain_head import AuditChainHead
from app.models.audit_log import AuditLog
from app.models.enums import AuditEventType

GENESIS_HASH = "0" * 64
_FORBIDDEN_METADATA_TERMS = (
    "password", "token", "secret", "recovery", "access_url", "access-link",
    "document", "content", "filename", "email", "full_name", "qr", "mfa_key",
)


@dataclass(frozen=True)
class AuditIntegrityResult:
    valid: bool
    checked_events: int
    first_invalid_sequence: int | None = None


def utcnow() -> datetime:
    return datetime.now(UTC)


def _canonical_payload(
    *, event_id: uuid.UUID, organization_id: uuid.UUID, sequence: int, previous_hash: str,
    created_at: datetime, actor_user_id: uuid.UUID | None, event_type: AuditEventType,
    entity_type: str | None, entity_id: uuid.UUID | None, metadata: dict[str, Any] | None,
    request_id_hash: str | None, correlation_id_hash: str | None, source_ip_hash: str | None,
) -> bytes:
    payload = {
        "actor_user_id": str(actor_user_id) if actor_user_id else None,
        "correlation_id_hash": correlation_id_hash,
        "created_at": created_at.astimezone(UTC).isoformat(),
        "entity_id": str(entity_id) if entity_id else None,
        "entity_type": entity_type,
        "event_id": str(event_id),
        "event_type": event_type.value,
        "metadata": metadata or {},
        "organization_id": str(organization_id),
        "previous_hash": previous_hash,
        "request_id_hash": request_id_hash,
        "sequence": sequence,
        "source_ip_hash": source_ip_hash,
    }
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _safe_metadata(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    """Keep bounded operational facts; free-form strings are never retained."""
    if not metadata:
        return None
    safe: dict[str, Any] = {}
    for raw_key, value in metadata.items():
        key = str(raw_key).lower()
        if any(term in key for term in _FORBIDDEN_METADATA_TERMS):
            continue
        if isinstance(value, bool) or value is None:
            safe[key] = value
        elif isinstance(value, int) and not isinstance(value, bool):
            safe[key] = value
        elif isinstance(value, float) and value.is_integer():
            safe[key] = int(value)
        elif isinstance(value, str):
            normalized = value.strip()
            if len(normalized) <= 80 and normalized and all(char.isupper() or char.isdigit() or char in "_-:." for char in normalized):
                safe[key] = normalized
    return safe or None


class AuditService:
    def __init__(self, db: Session):
        self.db = db

    def _locked_head(self, organization_id: uuid.UUID) -> AuditChainHead:
        head = self.db.execute(
            select(AuditChainHead).where(AuditChainHead.organization_id == organization_id).with_for_update()
        ).scalar_one_or_none()
        if head is None:
            # Existing tenants acquire their head lazily. The insert is
            # idempotent so two first requests cannot create competing chain
            # origins; the following FOR UPDATE obtains the sole cursor.
            self.db.execute(
                pg_insert(AuditChainHead)
                .values(
                    organization_id=organization_id,
                    last_sequence=0,
                    last_hash=GENESIS_HASH,
                    retention_anchor_sequence=0,
                    retention_anchor_hash=GENESIS_HASH,
                )
                .on_conflict_do_nothing(index_elements=[AuditChainHead.organization_id])
            )
            head = self.db.execute(
                select(AuditChainHead).where(AuditChainHead.organization_id == organization_id).with_for_update()
            ).scalar_one()
        return head

    def record(
        self,
        *,
        organization_id: uuid.UUID | None,
        actor_user_id: uuid.UUID | None,
        event_type: AuditEventType,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        metadata: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> AuditLog:
        """Append without committing the caller's transaction.

        Each protected service writes the audit event before its own commit, so
        audit persistence failure rolls the business mutation back as well.
        """
        if organization_id is None:
            raise ValueError("Audit events must be scoped to an organization")
        head = self._locked_head(organization_id)
        event_id = uuid.uuid4()
        sequence = head.last_sequence + 1
        created_at = utcnow()
        request = get_audit_context()
        safe_metadata = _safe_metadata(metadata)
        correlation_id_hash = fingerprint(correlation_id) if correlation_id else request.correlation_id_hash
        event_hash = hashlib.sha256(
            _canonical_payload(
                event_id=event_id,
                organization_id=organization_id,
                sequence=sequence,
                previous_hash=head.last_hash,
                created_at=created_at,
                actor_user_id=actor_user_id,
                event_type=event_type,
                entity_type=entity_type,
                entity_id=entity_id,
                metadata=safe_metadata,
                request_id_hash=request.request_id_hash,
                correlation_id_hash=correlation_id_hash,
                source_ip_hash=request.source_ip_hash,
            )
        ).hexdigest()
        entry = AuditLog(
            id=event_id,
            created_at=created_at,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            event_metadata=safe_metadata,
            sequence=sequence,
            previous_hash=head.last_hash,
            event_hash=event_hash,
            request_id_hash=request.request_id_hash,
            correlation_id_hash=correlation_id_hash,
            source_ip_hash=request.source_ip_hash,
        )
        self.db.add(entry)
        head.last_sequence = sequence
        head.last_hash = event_hash
        self.db.flush()
        return entry

    def list(
        self,
        organization_id: uuid.UUID,
        *,
        offset: int,
        limit: int,
        occurred_from: datetime | None = None,
        occurred_to: datetime | None = None,
        action: AuditEventType | None = None,
        actor_user_id: uuid.UUID | None = None,
        target_type: str | None = None,
        target_id: uuid.UUID | None = None,
    ) -> tuple[list[AuditLog], int]:
        filters = [AuditLog.organization_id == organization_id]
        if occurred_from:
            filters.append(AuditLog.created_at >= occurred_from)
        if occurred_to:
            filters.append(AuditLog.created_at <= occurred_to)
        if action:
            filters.append(AuditLog.event_type == action)
        if actor_user_id:
            filters.append(AuditLog.actor_user_id == actor_user_id)
        if target_type:
            filters.append(AuditLog.entity_type == target_type)
        if target_id:
            filters.append(AuditLog.entity_id == target_id)
        stmt = select(AuditLog).where(*filters).order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        total = int(self.db.scalar(select(func.count()).select_from(AuditLog).where(*filters)) or 0)
        return list(self.db.execute(stmt.offset(offset).limit(limit)).scalars().all()), total

    def verify(self, organization_id: uuid.UUID) -> AuditIntegrityResult:
        head = self.db.get(AuditChainHead, organization_id)
        if head is None:
            return AuditIntegrityResult(valid=True, checked_events=0)
        previous_hash = head.retention_anchor_hash
        expected_sequence = head.retention_anchor_sequence + 1
        events = self.db.execute(
            select(AuditLog)
            .where(AuditLog.organization_id == organization_id, AuditLog.sequence.is_not(None))
            .order_by(AuditLog.sequence)
        ).scalars().all()
        for index, event in enumerate(events, start=1):
            if event.sequence != expected_sequence or event.previous_hash != previous_hash:
                return AuditIntegrityResult(False, index, event.sequence)
            expected_hash = hashlib.sha256(
                _canonical_payload(
                    event_id=event.id,
                    organization_id=organization_id,
                    sequence=event.sequence,
                    previous_hash=event.previous_hash,
                    created_at=event.created_at,
                    actor_user_id=event.actor_user_id,
                    event_type=event.event_type,
                    entity_type=event.entity_type,
                    entity_id=event.entity_id,
                    metadata=event.event_metadata,
                    request_id_hash=event.request_id_hash,
                    correlation_id_hash=event.correlation_id_hash,
                    source_ip_hash=event.source_ip_hash,
                )
            ).hexdigest()
            if event.event_hash != expected_hash:
                return AuditIntegrityResult(False, index, event.sequence)
            previous_hash = event.event_hash
            expected_sequence += 1
        if events and (head.last_hash != previous_hash or head.last_sequence != events[-1].sequence):
            return AuditIntegrityResult(False, len(events), events[-1].sequence)
        return AuditIntegrityResult(True, len(events))

    def cleanup_expired(self, retention_days: int) -> int:
        """Checkpoint and prune old events without severing retained chains."""
        cutoff = utcnow() - timedelta(days=retention_days)
        deleted_count = 0
        for organization_id in self.db.execute(select(AuditChainHead.organization_id)).scalars().all():
            head = self._locked_head(organization_id)
            candidates = self.db.execute(
                select(AuditLog)
                .where(
                    AuditLog.organization_id == organization_id,
                    AuditLog.sequence.is_not(None),
                    AuditLog.sequence > head.retention_anchor_sequence,
                    AuditLog.created_at < cutoff,
                )
                .order_by(AuditLog.sequence)
            ).scalars().all()
            if not candidates:
                continue
            anchor = candidates[-1]
            self.record(
                organization_id=organization_id,
                actor_user_id=None,
                event_type=AuditEventType.AUDIT_RETENTION_CHECKPOINT,
                entity_type="audit_log",
                metadata={"purged_event_count": len(candidates), "purged_through_sequence": anchor.sequence},
            )
            head.retention_anchor_sequence = anchor.sequence
            head.retention_anchor_hash = anchor.event_hash or GENESIS_HASH
            self.db.execute(delete(AuditLog).where(AuditLog.id.in_([event.id for event in candidates])))
            deleted_count += len(candidates)
        self.db.commit()
        return deleted_count
