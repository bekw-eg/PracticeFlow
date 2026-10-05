import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.models.enums import InternshipStatus


class CreateInternshipRequest(BaseModel):
    title: str
    description: str | None = Field(default=None, max_length=2000)
    template_version_id: uuid.UUID
    specialty_id: uuid.UUID | None = None
    start_date: date
    end_date: date
    deadline: date


class InternshipOut(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    status: InternshipStatus
    template_version_id: uuid.UUID
    start_date: date
    end_date: date
    deadline: date
    created_at: datetime

    model_config = {"from_attributes": True}


class UpdateInternshipRequest(BaseModel):
    title: str | None = None
    description: str | None = Field(default=None, max_length=2000)
    start_date: date | None = None
    end_date: date | None = None
    deadline: date | None = None


class GroupReportProgress(BaseModel):
    total: int
    draft: int
    submitted: int
    under_review: int
    revision_required: int
    locked: int
