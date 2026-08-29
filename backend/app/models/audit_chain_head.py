import uuid

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class AuditChainHead(TimestampMixin, Base):
    """One locked hash-chain cursor per organization."""

    __tablename__ = "audit_chain_heads"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True
    )
    last_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    retention_anchor_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retention_anchor_hash: Mapped[str] = mapped_column(String(64), nullable=False)
