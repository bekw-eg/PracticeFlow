import uuid

from pydantic import BaseModel, Field


class StudentProfileGroupOut(BaseModel):
    id: uuid.UUID
    name: str
    academic_year: str | None


class StudentProfileOut(BaseModel):
    student_id: uuid.UUID
    full_name: str
    email: str
    specialty_name: str | None
    groups: list[StudentProfileGroupOut]
    reports_count: int


class UpdateProfileRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=255)
