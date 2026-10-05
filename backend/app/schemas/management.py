import uuid
from datetime import date

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.security import validate_password
from app.models.enums import InternshipStatus, ReportStatus, RoleName


class OrganizationOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str

    model_config = {"from_attributes": True}


class ManagementOverview(BaseModel):
    organization: OrganizationOut
    members_count: int
    students_count: int
    teachers_count: int
    groups_count: int
    active_reports_count: int


class DirectorReportStatusCount(BaseModel):
    """A safe, tenant-scoped total for one report workflow status."""

    status: ReportStatus
    count: int


class DirectorGroupSummary(BaseModel):
    """Operational group information that does not expose student reports."""

    id: uuid.UUID
    name: str
    academic_year: str | None
    student_count: int
    internships_count: int
    reports_count: int
    overdue_reports_count: int


class DirectorInternshipSummary(BaseModel):
    """Read-only internship progress metadata for a Director."""

    id: uuid.UUID
    title: str
    group_id: uuid.UUID
    group_name: str
    status: InternshipStatus
    start_date: date
    end_date: date
    deadline: date
    reports_count: int
    overdue_reports_count: int


class DirectorTeacherLoad(BaseModel):
    """Workload totals only; no report or comment content is included."""

    id: uuid.UUID
    full_name: str
    groups_count: int
    active_internships_count: int
    reports_to_review_count: int


class DirectorDashboard(BaseModel):
    """Read-only tenant dashboard deliberately limited to operational data."""

    organization: OrganizationOut
    groups_count: int
    internships_count: int
    active_internships_count: int
    reports_count: int
    overdue_reports_count: int
    report_statuses: list[DirectorReportStatusCount]
    groups: list[DirectorGroupSummary]
    internships: list[DirectorInternshipSummary]
    teacher_loads: list[DirectorTeacherLoad]


class DepartmentOut(BaseModel):
    id: uuid.UUID
    name: str

    model_config = {"from_attributes": True}


class SpecialtyOut(BaseModel):
    id: uuid.UUID
    name: str
    code: str | None
    department_id: uuid.UUID

    model_config = {"from_attributes": True}


class MemberOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    full_name: str
    email: str
    role: RoleName
    profile_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    specialty_id: uuid.UUID | None = None
    group_names: list[str] = []
    is_active: bool


class CreateMemberRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    role: RoleName
    password: str | None = None
    department_id: uuid.UUID | None = None
    specialty_id: uuid.UUID | None = None

    @field_validator("password")
    @classmethod
    def password_policy(cls, value: str | None) -> str | None:
        return validate_password(value) if value is not None else None


class UpdateMemberRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=255)
    role: RoleName | None = None
    department_id: uuid.UUID | None = None
    specialty_id: uuid.UUID | None = None
    is_active: bool | None = None


class CreateGroupRequest(BaseModel):
    name: str = Field(min_length=2, max_length=50)
    academic_year: str | None = Field(default=None, max_length=20)
    specialty_id: uuid.UUID | None = None
    teacher_ids: list[uuid.UUID] = []


class ManagementGroupOut(BaseModel):
    id: uuid.UUID
    name: str
    academic_year: str | None
    specialty_id: uuid.UUID | None
    student_count: int
    teacher_ids: list[uuid.UUID]
    teacher_names: list[str]


class AssignTeachersRequest(BaseModel):
    teacher_ids: list[uuid.UUID] = Field(min_length=1)


class CreateDepartmentRequest(BaseModel):
    name: str = Field(min_length=2, max_length=255)


class CreateSpecialtyRequest(BaseModel):
    department_id: uuid.UUID
    name: str = Field(min_length=2, max_length=255)
    code: str | None = Field(default=None, max_length=50)


class CatalogOut(BaseModel):
    departments: list[DepartmentOut]
    specialties: list[SpecialtyOut]


class CreateOrganizationRequest(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    slug: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
