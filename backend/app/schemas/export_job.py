import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.enums import ExportFormat, ExportJobStatus


class ExportJobCreated(BaseModel):
    job_id: uuid.UUID
    status: ExportJobStatus
    reused_active_job: bool = False


class ExportJobOut(BaseModel):
    id: uuid.UUID
    report_id: uuid.UUID
    format: ExportFormat
    status: ExportJobStatus
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    expires_at: datetime | None
    error_code: str | None = None
    download_url: str | None = None

    model_config = {"from_attributes": True}
