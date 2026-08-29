import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.documents.schemas import DocumentModel


class CreateTemplateRequest(BaseModel):
    name: str
    description: str | None = None


class CreateTemplateVersionRequest(BaseModel):
    """No document content here — a new version starts from the standard
    academic skeleton (app/documents/defaults.py) and is then edited via
    PATCH .../document. Kept as its own (currently empty) schema rather than
    an empty POST body so it's a natural place to add version-level metadata
    later (e.g. a "copy from version N" option) without an API shape change.
    """

    pass


class TemplateVersionSummary(BaseModel):
    id: uuid.UUID
    version_number: int
    is_published: bool
    is_locked: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TemplateVersionDetail(TemplateVersionSummary):
    document: DocumentModel
    numbering: dict[str, str]
    revision: int


class UpdateTemplateVersionDocumentRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    document: DocumentModel


class TemplateOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    versions: list[TemplateVersionSummary]

    model_config = {"from_attributes": True}
