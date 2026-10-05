import uuid

from sqlalchemy import func, select

from app.models.file import File
from app.models.discipline import TeachingMaterial
from app.models.document_check import StudentDocumentSubmission, TeacherDocumentSubmission, TeacherDocumentLifecycle
from app.repositories.base import TenantScopedRepository


class FileRepository(TenantScopedRepository[File]):
    model = File

    def total_size_bytes(self, organization_id: uuid.UUID) -> int:
        # Both product flows share one tenant storage budget. Original DOCX
        # metadata stays in its domain table rather than masquerading as an
        # editor image File.
        image_bytes = int(
            self.db.scalar(
                select(func.coalesce(func.sum(File.size_bytes), 0)).where(File.organization_id == organization_id)
            )
            or 0
        )
        submission_bytes = int(
            self.db.scalar(
                select(func.coalesce(func.sum(StudentDocumentSubmission.size_bytes), 0)).where(
                    StudentDocumentSubmission.organization_id == organization_id,
                )
            )
            or 0
        )
        teacher_submission_bytes = int(
            self.db.scalar(
                select(func.coalesce(func.sum(TeacherDocumentSubmission.size_bytes), 0)).where(
                    TeacherDocumentSubmission.organization_id == organization_id,
                    ~TeacherDocumentSubmission.lifecycle.has(TeacherDocumentLifecycle.original_deleted_at.is_not(None)),
                )
            )
            or 0
        )
        material_bytes = int(self.db.scalar(select(func.coalesce(func.sum(TeachingMaterial.size_bytes), 0)).where(
            TeachingMaterial.organization_id == organization_id,
            TeachingMaterial.storage_deleted_at.is_(None),
        )) or 0)
        return image_bytes + submission_bytes + teacher_submission_bytes + material_bytes
