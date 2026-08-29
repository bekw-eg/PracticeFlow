import uuid

from pydantic import BaseModel


class GroupSummary(BaseModel):
    id: uuid.UUID
    name: str
    academic_year: str | None
    student_count: int

    model_config = {"from_attributes": True}


class GroupMemberOut(BaseModel):
    id: uuid.UUID
    student_id: uuid.UUID
    full_name: str
    email: str

    model_config = {"from_attributes": True}


class GroupDetail(BaseModel):
    id: uuid.UUID
    name: str
    academic_year: str | None
    students: list[GroupMemberOut]

    model_config = {"from_attributes": True}


class AddGroupMemberRequest(BaseModel):
    student_id: uuid.UUID


class StudentOptionOut(BaseModel):
    id: uuid.UUID
    full_name: str
    email: str
    specialty_name: str | None
