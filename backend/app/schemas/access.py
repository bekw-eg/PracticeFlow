import uuid
from pydantic import BaseModel, Field, field_validator

from app.core.security import validate_password


class AccessLinkOut(BaseModel):
    purpose: str
    access_url: str
    delivery: str


class CompleteAccessRequest(BaseModel):
    token: str = Field(min_length=20)
    password: str

    @field_validator("password")
    @classmethod
    def password_policy(cls, value: str) -> str:
        return validate_password(value)


class OrganizationChoice(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    role: str

    model_config = {"from_attributes": True}


class SwitchOrganizationRequest(BaseModel):
    organization_id: uuid.UUID
