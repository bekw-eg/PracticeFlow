import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.enums import InternshipStatus, ReportStatus


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


class StudentRiskItem(BaseModel):
    student_id: uuid.UUID
    student_name: str
    internship_id: uuid.UUID
    internship_title: str
    report_id: uuid.UUID
    report_status: ReportStatus
    deadline: date
    completion_percent: int | None
    days_since_activity: int
    level: Literal["GREEN", "YELLOW", "RED"]
    reasons: list[str]


class GroupStudentRisk(BaseModel):
    red: int
    yellow: int
    green: int
    items: list[StudentRiskItem]
