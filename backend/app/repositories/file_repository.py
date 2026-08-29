import uuid

from sqlalchemy import func, select

from app.models.file import File
from app.repositories.base import TenantScopedRepository


class FileRepository(TenantScopedRepository[File]):
    model = File

    def total_size_bytes(self, organization_id: uuid.UUID) -> int:
        return int(
            self.db.scalar(
                select(func.coalesce(func.sum(File.size_bytes), 0)).where(File.organization_id == organization_id)
            )
            or 0
        )
