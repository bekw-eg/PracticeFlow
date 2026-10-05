"""Teacher-owned curriculum, separate from internships and document checks."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class Discipline(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "disciplines"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_disciplines_org_id"),
        ForeignKeyConstraint(["created_by_user_id", "organization_id"],
                             ["organization_memberships.user_id", "organization_memberships.organization_id"],
                             ondelete="RESTRICT", name="fk_discipline_owner_membership"),
        Index("ix_disciplines_owner_archive", "organization_id", "created_by_user_id", "is_archived", "created_at", "id"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    academic_year: Mapped[str | None] = mapped_column(String(20))
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")


class DisciplineGroup(Base):
    __tablename__ = "discipline_groups"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id", "discipline_id"], ["disciplines.organization_id", "disciplines.id"],
                             ondelete="CASCADE", name="fk_discipline_group_discipline"),
        ForeignKeyConstraint(["organization_id", "group_id"], ["groups.organization_id", "groups.id"],
                             ondelete="CASCADE", name="fk_discipline_group_group"),
        Index("ix_discipline_groups_group", "organization_id", "group_id"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    discipline_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    group_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)


class DisciplineTopic(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "discipline_topics"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id", "discipline_id"], ["disciplines.organization_id", "disciplines.id"],
                             ondelete="RESTRICT", name="fk_topic_discipline"),
        UniqueConstraint("organization_id", "discipline_id", "id", name="uq_topics_org_discipline_id"),
        CheckConstraint("position >= 0", name="ck_topic_position"),
        Index("ix_topics_discipline_position", "organization_id", "discipline_id", "is_archived", "position", "id"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    discipline_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    learning_goal: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")


class TeachingMaterial(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "teaching_materials"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id", "discipline_id", "topic_id"],
                             ["discipline_topics.organization_id", "discipline_topics.discipline_id", "discipline_topics.id"],
                             ondelete="RESTRICT", name="fk_material_topic"),
        ForeignKeyConstraint(["uploaded_by_user_id", "organization_id"],
                             ["organization_memberships.user_id", "organization_memberships.organization_id"],
                             ondelete="RESTRICT", name="fk_material_uploader_membership"),
        UniqueConstraint("storage_key", name="uq_teaching_material_storage_key"),
        UniqueConstraint("organization_id", "topic_id", "uploaded_by_user_id", "idempotency_key", name="uq_material_upload_request"),
        CheckConstraint("size_bytes > 0", name="ck_material_size"),
        CheckConstraint("storage_deleted_at IS NULL OR deleted_at IS NOT NULL", name="ck_material_deletion"),
        Index("ix_materials_topic_created", "organization_id", "topic_id", "deleted_at", "created_at", "id"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    discipline_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    topic_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(127), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    storage_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
