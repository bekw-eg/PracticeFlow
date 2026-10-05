import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import CheckRuleType


class GroupReportCreate(BaseModel):
    request_id: uuid.UUID
    locale: Literal["ru", "kk", "en"] = "ru"
    model_config = ConfigDict(extra="forbid")


class GroupReportWrite(BaseModel):
    revision: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=500)
    introduction: str = Field(max_length=10000)
    conclusions: str = Field(max_length=20000)
    selected_rule_types: list[CheckRuleType] = Field(max_length=50)
    finding_ids: list[uuid.UUID] = Field(max_length=30)
    remark_submission_ids: list[uuid.UUID] = Field(max_length=30)
    model_config = ConfigDict(extra="forbid")


class GroupReportExport(BaseModel):
    revision: int = Field(ge=1)
    model_config = ConfigDict(extra="forbid")


class GroupReportOut(BaseModel):
    id: uuid.UUID
    group_id: uuid.UUID
    locale: str
    revision: int
    created_at: datetime
    generated_at: datetime | None
    snapshot: dict
    content: dict
    model_config = ConfigDict(from_attributes=True)


class GroupReportListOut(BaseModel):
    id: uuid.UUID
    locale: str
    revision: int
    title: str
    created_at: datetime
    generated_at: datetime | None


class ReportFindingOut(BaseModel):
    id: uuid.UUID
    rule_type: CheckRuleType
    location: dict
    actual: dict
    expected: dict
