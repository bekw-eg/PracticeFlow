import uuid
from datetime import datetime

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


class ReportDetail(ReportOut):
    versions: list[ReportVersionOut]
    deadline: str


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
