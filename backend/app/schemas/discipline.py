import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=5000)]
AcademicYear = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20)]


class DisciplineCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Name
    description: Description | None = None
    academic_year: AcademicYear | None = None
    group_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)


class DisciplineUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Name | None = None
    description: Description | None = None
    academic_year: AcademicYear | None = None
    group_ids: list[uuid.UUID] | None = Field(default=None, max_length=100)
    is_archived: bool | None = None

    @model_validator(mode="after")
    def non_null_fields(self):
        for field in ("name", "group_ids", "is_archived"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class DisciplineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    description: str | None
    academic_year: str | None
    is_archived: bool
    created_at: datetime
    updated_at: datetime


class DisciplineGroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    academic_year: str | None


class TopicCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Name
    description: Description | None = None
    learning_goal: Description | None = None
    position: int | None = Field(default=None, ge=0, le=1000000)


class TopicUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Name | None = None
    description: Description | None = None
    learning_goal: Description | None = None
    position: int | None = Field(default=None, ge=0, le=1000000)
    is_archived: bool | None = None

    @model_validator(mode="after")
    def non_null_fields(self):
        for field in ("title", "position", "is_archived"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class TopicOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    discipline_id: uuid.UUID
    title: str
    description: str | None
    learning_goal: str | None
    position: int
    is_archived: bool
    created_at: datetime
    updated_at: datetime


class MaterialOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    discipline_id: uuid.UUID
    topic_id: uuid.UUID
    title: str
    original_filename: str
    content_type: str
    size_bytes: int
    sha256: str
    created_at: datetime
