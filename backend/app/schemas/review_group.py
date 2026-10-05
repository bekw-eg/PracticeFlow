import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.models.enums import CheckRuleType


class ReviewGroupWrite(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=5000)] | None = None
    model_config = ConfigDict(extra="forbid")


class ReviewGroupOut(ReviewGroupWrite):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class TeacherReviewWrite(BaseModel):
    revision: int = Field(ge=0)
    remarks: str = Field(max_length=10000)
    model_config = ConfigDict(extra="forbid")


class TeacherReviewComplete(TeacherReviewWrite):
    job_id: uuid.UUID


class TeacherReviewOut(BaseModel):
    revision: int
    remarks: str
    completed_at: datetime | None
    completed_by_teacher_id: uuid.UUID | None
    completed_job_id: uuid.UUID | None
    model_config = ConfigDict(from_attributes=True)


ReviewStatus = Literal["pending", "completed"]
WorkType = Literal["COURSEWORK", "REPORT"]


class ViolationCount(BaseModel):
    rule_type: CheckRuleType
    violations_count: int
    works_count: int


class ReviewGroupSummary(BaseModel):
    total_works: int
    pending_works: int
    reviewed_works: int
    included_works: int
    truncated_works: int
    violations: list[ViolationCount]
