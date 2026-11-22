import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.discipline import TeachingMaterial
from app.models.document_check import TeacherDocumentLifecycle, TeacherDocumentSubmission


class FileRepository:
    def __init__(self, db: Session):
        self.db = db

    def total_size_bytes(self, organization_id: uuid.UUID) -> int:
        """Compute active tenant storage usage across document checks and teaching materials."""
        teacher_submission_bytes = int(
            self.db.scalar(
                select(func.coalesce(func.sum(TeacherDocumentSubmission.size_bytes), 0)).where(
                    TeacherDocumentSubmission.organization_id == organization_id,
                    ~TeacherDocumentSubmission.lifecycle.has(TeacherDocumentLifecycle.original_deleted_at.is_not(None)),
                )
            )
            or 0
        )
        material_bytes = int(
            self.db.scalar(
                select(func.coalesce(func.sum(TeachingMaterial.size_bytes), 0)).where(
                    TeachingMaterial.organization_id == organization_id,
                    TeachingMaterial.storage_deleted_at.is_(None),
                )
            )
            or 0
        )
        return teacher_submission_bytes + material_bytes
