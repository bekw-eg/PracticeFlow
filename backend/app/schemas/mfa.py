import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class MfaChallengeResponse(BaseModel):
    status: Literal["MFA_REQUIRED", "MFA_ENROLLMENT_REQUIRED", "MFA_RECOVERY_PENDING"]
    challenge_id: uuid.UUID
    expires_at: datetime


class MfaCodeRequest(BaseModel):
    challenge_id: uuid.UUID
    code: str = Field(min_length=6, max_length=32)


class MfaEnrollmentStartRequest(BaseModel):
    challenge_id: uuid.UUID


class MfaEnrollmentStartResponse(BaseModel):
    challenge_id: uuid.UUID
    expires_at: datetime
    manual_key: str
    qr_data_url: str


class MfaEnrollmentCompleteResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    recovery_codes: list[str]


class MfaRecoveryRequest(BaseModel):
    challenge_id: uuid.UUID
    recovery_code: str = Field(min_length=6, max_length=32)


class MfaPeerRecoveryRequest(BaseModel):
    challenge_id: uuid.UUID


class MfaPeerRecoveryStatus(BaseModel):
    status: Literal["MFA_RECOVERY_PENDING", "MFA_ENROLLMENT_REQUIRED"]
    challenge_id: uuid.UUID
    expires_at: datetime
    approved: bool


class MfaRecoveryRequestOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    user_email: str
    user_name: str
    expires_at: datetime
    created_at: datetime


class MfaBreakGlassStartRequest(BaseModel):
    challenge_id: uuid.UUID
    enrollment_code: str = Field(min_length=12, max_length=128)
