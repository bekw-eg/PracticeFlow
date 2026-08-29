import uuid

from sqlalchemy import Boolean, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class OrganizationMembership(UUIDPKMixin, TimestampMixin, Base):
    """The single source of truth for 'which org does this user act in, and as what role'.

    Tenant context for every authenticated request is derived from this table —
    never from a client-supplied organization_id.
    """

    __tablename__ = "organization_memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "organization_id", name="uq_membership_user_org"),
        Index("ix_memberships_org_created_id", "organization_id", "created_at", "id"),
        Index("ix_memberships_user_active_org", "user_id", "is_active", "organization_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    role_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("roles.id"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    user: Mapped["User"] = relationship(back_populates="memberships")
    organization: Mapped["Organization"] = relationship(back_populates="memberships")
    role: Mapped["Role"] = relationship(back_populates="memberships")

    teacher_profile: Mapped["Teacher"] = relationship(back_populates="membership", uselist=False)
    student_profile: Mapped["Student"] = relationship(back_populates="membership", uselist=False)
