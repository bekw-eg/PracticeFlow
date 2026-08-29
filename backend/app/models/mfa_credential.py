import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class MfaCredential(UUIDPKMixin, TimestampMixin, Base):
    """One user-owned TOTP factor.

    The secret is encrypted before it reaches this table. ``security_version``
    invalidates all MFA-authenticated sessions whenever a factor is reset.
    """

    __tablename__ = "mfa_credentials"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    enabled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    security_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_totp_counter: Mapped[int | None] = mapped_column(Integer, nullable=True)
