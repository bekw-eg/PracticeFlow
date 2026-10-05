import re
import uuid
from contextlib import suppress
from datetime import UTC, datetime

from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dependencies.auth import RequestContext
from app.models.discipline import Discipline, DisciplineTopic, TeachingMaterial
from app.models.enums import AuditEventType
from app.permissions.disciplines import require_curriculum_teacher
from app.repositories.discipline_repository import DisciplineRepository
from app.repositories.file_repository import FileRepository
from app.repositories.group_repository import GroupRepository
from app.resource_protection import ResourceGuard
from app.schemas.discipline import DisciplineCreate, DisciplineUpdate, TopicCreate, TopicUpdate
from app.services.audit_service import AuditService
from app.services.teaching_material_preflight import material_error, stage_material
from app.storage import get_storage_service
from app.storage.base import StorageUnavailableError


def missing() -> HTTPException:
    return HTTPException(status_code=404, detail="Discipline, topic or material not found")


class DisciplineService:
    def __init__(self, db: Session, guard: ResourceGuard | None = None):
        self.db = db
        self.repo = DisciplineRepository(db)
        self.guard = guard
        self.storage = get_storage_service()

    def get(self, ctx: RequestContext, discipline_id: uuid.UUID, *, lock: bool = False):
        require_curriculum_teacher(ctx)
        row = self.repo.get(ctx, discipline_id, lock=lock)
        if row is None:
            raise missing()
        return row

    def list(self, ctx, archived, offset, limit):
        require_curriculum_teacher(ctx)
        return self.repo.disciplines(ctx, archived, offset, limit)

    def _validate_groups(self, ctx, ids):
        repo = GroupRepository(self.db)
        for value in set(ids):
            if repo.get(ctx.organization_id, value) is None or not repo.teacher_owns_group(self.db, ctx.teacher_id, value):
                raise missing()

    def create(self, ctx: RequestContext, payload: DisciplineCreate):
        require_curriculum_teacher(ctx)
        self._validate_groups(ctx, payload.group_ids)
        row = Discipline(organization_id=ctx.organization_id, created_by_user_id=ctx.user_id,
                         **payload.model_dump(exclude={"group_ids"}))
        self.db.add(row)
        self.db.flush()
        self.repo.replace_groups(ctx, row.id, payload.group_ids)
        self.db.commit()
        self.db.refresh(row)
        return row

    def update(self, ctx, discipline_id, payload: DisciplineUpdate):
        row = self.get(ctx, discipline_id, lock=True)
        values = payload.model_dump(exclude_unset=True)
        if "group_ids" in values:
            self._validate_groups(ctx, values["group_ids"])
            self.repo.replace_groups(ctx, row.id, values.pop("group_ids"))
        for key, value in values.items():
            setattr(row, key, value)
        self.db.commit()
        self.db.refresh(row)
        return row

    def groups(self, ctx, discipline_id):
        self.get(ctx, discipline_id)
        return self.repo.groups(ctx, discipline_id)

    @staticmethod
    def _active(discipline, topic=None):
        if discipline.is_archived or (topic is not None and topic.is_archived):
            raise material_error("CURRICULUM_ARCHIVED", "Restore the discipline or topic before editing.", 409)

    def topics(self, ctx, discipline_id, archived, offset, limit):
        self.get(ctx, discipline_id)
        return self.repo.topics(ctx, discipline_id, archived, offset, limit)

    def create_topic(self, ctx, discipline_id, payload: TopicCreate):
        parent = self.get(ctx, discipline_id, lock=True)
        self._active(parent)
        values = payload.model_dump()
        if values["position"] is None:
            values["position"] = self.repo.next_position(ctx.organization_id, discipline_id)
        row = DisciplineTopic(organization_id=ctx.organization_id, discipline_id=discipline_id, **values)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def topic(self, ctx, topic_id):
        require_curriculum_teacher(ctx)
        row = self.repo.topic(ctx, topic_id)
        if row is None:
            raise missing()
        return row

    def update_topic(self, ctx, topic_id, payload: TopicUpdate):
        row = self.topic(ctx, topic_id)
        parent = self.get(ctx, row.discipline_id, lock=True)
        self.db.refresh(row)
        # Archive/restore remains possible; editing archived content requires restore.
        values = payload.model_dump(exclude_unset=True)
        if set(values) - {"is_archived"}:
            self._active(parent, row)
        for key, value in values.items():
            setattr(row, key, value)
        self.db.commit()
        self.db.refresh(row)
        return row

    def materials(self, ctx, topic_id, offset, limit):
        self.topic(ctx, topic_id)
        return self.repo.materials(ctx, topic_id, offset, limit)

    def material(self, ctx, material_id, *, include_deleted=False):
        require_curriculum_teacher(ctx)
        row = self.repo.material(ctx, material_id, include_deleted=include_deleted)
        if row is None:
            raise missing()
        return row

    def _audit_file(self, ctx, row, event):
        AuditService(self.db).record(organization_id=ctx.organization_id, actor_user_id=ctx.user_id,
            event_type=event, entity_type="teaching_material", entity_id=row.id,
            metadata={"size_bytes": row.size_bytes})

    def upload(self, ctx, topic_id, upload: UploadFile, title: str | None, key: str):
        topic = self.topic(ctx, topic_id)
        if not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", key):
            raise material_error("IDEMPOTENCY_KEY_INVALID", "Invalid upload key.")
        title = title.strip() if title else None
        if title is not None and not 1 <= len(title) <= 255:
            raise material_error("MATERIAL_TITLE_INVALID", "Use a title of 1–255 characters.", 422)
        if self.guard is None:
            raise RuntimeError("A resource guard is required for material uploads")
        self.guard.check_upload_request(ctx.organization_id, ctx.user_id)
        with stage_material(upload) as validated:
            # Serialize mutations, archive, and upload retries on the same discipline.
            parent = self.get(ctx, topic.discipline_id, lock=True)
            self.db.refresh(topic)
            previous = self.repo.previous_upload(ctx, topic_id, key)
            normalized_title = title or validated.original_filename
            if previous is not None:
                if (previous.sha256, previous.original_filename, previous.title, previous.size_bytes) != (
                    validated.sha256, validated.original_filename, normalized_title, validated.size_bytes,
                ) or previous.deleted_at is not None:
                    raise material_error("IDEMPOTENCY_KEY_CONFLICT", "The upload key was already used.", 409)
                return previous, False
            self._active(parent, topic)
            reservation = self.guard.reserve_upload(ctx.organization_id, ctx.user_id, validated.size_bytes,
                                                    FileRepository(self.db).total_size_bytes(ctx.organization_id))
            material_id = uuid.uuid4()
            storage_key = (f"orgs/{ctx.organization_id}/teaching-materials/{parent.id}/{topic_id}/"
                           f"{material_id}/{validated.sha256}.{validated.extension}")
            saved = False
            try:
                self.storage.save_new(storage_key, validated.stream, validated.content_type)
                saved = True
                row = TeachingMaterial(id=material_id, organization_id=ctx.organization_id, discipline_id=parent.id,
                    topic_id=topic_id, uploaded_by_user_id=ctx.user_id, title=normalized_title,
                    storage_key=storage_key, content_type=validated.content_type, size_bytes=validated.size_bytes,
                    sha256=validated.sha256, original_filename=validated.original_filename, idempotency_key=key)
                self.db.add(row)
                self.db.flush()
                self._audit_file(ctx, row, AuditEventType.FILE_GENERATED)
                self.db.commit()
            except Exception as exc:
                self.db.rollback()
                # A lost commit acknowledgement must never delete an accepted file.
                if saved:
                    with suppress(Exception):
                        with Session(self.db.get_bind()) as verification:
                            accepted = verification.scalar(select(TeachingMaterial.id).where(
                                TeachingMaterial.organization_id == ctx.organization_id, TeachingMaterial.id == material_id))
                        if accepted is None:
                            self.storage.delete(storage_key)
                with suppress(Exception):
                    self.guard.cancel_upload(reservation)
                raise material_error("MATERIAL_STORAGE_UNAVAILABLE" if isinstance(exc, StorageUnavailableError)
                                     else "MATERIAL_SAVE_UNAVAILABLE", "The material could not be saved. Retry the upload.", 503) from None
            with suppress(Exception):
                self.guard.complete_upload(reservation)
            self.db.refresh(row)
            return row, True

    def download(self, ctx, material_id):
        row = self.material(ctx, material_id)
        try:
            stream = self.storage.open(row.storage_key)
        except (StorageUnavailableError, FileNotFoundError, OSError):
            raise material_error("MATERIAL_STORAGE_UNAVAILABLE", "File storage is temporarily unavailable.", 503) from None
        try:
            self._audit_file(ctx, row, AuditEventType.FILE_DOWNLOADED)
            self.db.commit()
            return row, stream
        except Exception:
            stream.close()
            self.db.rollback()
            raise

    def delete_material(self, ctx, material_id):
        row = self.material(ctx, material_id, include_deleted=True)
        self.get(ctx, row.discipline_id, lock=True)
        self.db.refresh(row)
        if row.storage_deleted_at is not None:
            return
        if row.deleted_at is None:
            row.deleted_at = datetime.now(UTC)
            self._audit_file(ctx, row, AuditEventType.FILE_DELETED)
            self.db.commit()
        # Metadata is retained for retry/reconciliation; all GETs already return 404.
        try:
            self.storage.delete(row.storage_key)
            row.storage_deleted_at = datetime.now(UTC)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise material_error("MATERIAL_DELETE_PENDING", "Access is revoked; retry deletion to remove the stored file.", 503) from None
