import uuid

from pydantic import BaseModel, Field


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


class BulkStudentOperationRequest(BaseModel):
    """A bounded, explicit list keeps one bulk request auditable and safe."""

    student_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)


class BulkTransferStudentsRequest(BulkStudentOperationRequest):
    target_group_id: uuid.UUID


class BulkStudentOperationFailure(BaseModel):
    student_id: uuid.UUID
    code: str


class BulkStudentOperationResult(BaseModel):
    succeeded_student_ids: list[uuid.UUID]
    failed: list[BulkStudentOperationFailure]


class StudentOptionOut(BaseModel):
    id: uuid.UUID
    full_name: str
    email: str
    specialty_name: str | None
