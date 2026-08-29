import uuid

from pydantic import BaseModel, EmailStr, field_validator

from app.core.security import validate_password


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    organization_slug: str

    @field_validator("password")
    @classmethod
    def password_policy(cls, value: str) -> str:
        return validate_password(value)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CurrentUserResponse(BaseModel):
    user_id: uuid.UUID
    organization_id: uuid.UUID
    full_name: str
    email: str
    role: str

    model_config = {"from_attributes": True}
