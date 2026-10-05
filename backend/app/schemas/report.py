import uuid
from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field

from app.documents.schemas import Block, DocumentModel
from app.models.enums import ReportStatus


class ReportVersionOut(BaseModel):
    id: uuid.UUID
    version_number: int
    submitted_at: datetime
    is_late: bool

    model_config = {"from_attributes": True}


class ReportOut(BaseModel):
    id: uuid.UUID
    internship_id: uuid.UUID
    student_id: uuid.UUID
    status: ReportStatus
    current_version_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ReportDeadlineState(str, Enum):
    UPCOMING = "UPCOMING"
    DUE_SOON = "DUE_SOON"
    DUE_TODAY = "DUE_TODAY"
    OVERDUE = "OVERDUE"
    SUBMITTED_ON_TIME = "SUBMITTED_ON_TIME"
    SUBMITTED_LATE = "SUBMITTED_LATE"


class ReviewQueueDeadlineFilter(str, Enum):
    OVERDUE = "overdue"
    DUE_TODAY = "due_today"
    DUE_SOON = "due_soon"
    UPCOMING = "upcoming"


class StudentReportOut(ReportOut):
    """Compact student-only list item. It intentionally excludes the report
    document and exposes only the internship context needed by the list UI."""

    internship_title: str
    internship_description: str | None
    group_name: str
    start_date: date
    end_date: date
    deadline: date
    deadline_state: ReportDeadlineState


class TeacherReviewQueueItem(ReportOut):
    """Teacher-facing queue metadata. The report document stays out of this
    list endpoint and remains available only through the existing review API."""

    student_name: str
    internship_title: str
    deadline: date
    is_overdue: bool
    submitted_late: bool
    open_comments_count: int


class ReportDetail(ReportOut):
    versions: list[ReportVersionOut]
    deadline: str
    internship_title: str


class ReportDocumentResponse(BaseModel):
    document: DocumentModel
    numbering: dict[str, str]
    editable: bool
    revision: int


class UpdateReportDocumentRequest(BaseModel):
    """Keyed by section id -> the section's replacement block list.
    Deliberately cannot express changes to meta/titlePage/header/footer/the
    section list itself — that boundary is enforced by the shape of this
    request, not just by a runtime check (rule 15/16)."""

    expected_revision: int = Field(ge=1)
    sections: dict[str, list[Block]]


class ReportHistoryEntry(BaseModel):
    event: str
    actor_name: str | None
    actor_role: str | None
    created_at: datetime
    metadata: dict | None
