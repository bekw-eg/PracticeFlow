import uuid
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.db.session import get_db
from app.repositories.membership_repository import MembershipRepository
from app.repositories.student_repository import StudentRepository
from app.repositories.teacher_repository import TeacherRepository
from app.repositories.user_repository import UserRepository
from app.services.mfa_service import MfaService, role_requires_mfa

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class RequestContext:
    """Everything a request handler needs about 'who is calling, in what org, as what role'.

    Deliberately re-derived from the database on every request (not just decoded
    from the JWT) — the access token's org_id/role claims are only a hint of
    intent; membership + role are the source of truth, so a revoked membership
    or changed role takes effect immediately rather than waiting for token expiry.
    """

    user_id: uuid.UUID
    organization_id: uuid.UUID
    role: str
    membership_id: uuid.UUID
    teacher_id: uuid.UUID | None = None
    student_id: uuid.UUID | None = None


def _credentials_exception() -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")


def get_current_context(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> RequestContext:
    if credentials is None:
        raise _credentials_exception()

    try:
        payload = decode_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise _credentials_exception()

    if payload.get("type") != "access":
        raise _credentials_exception()

    user_id_raw = payload.get("sub")
    org_id_raw = payload.get("org_id")
    if not user_id_raw or not org_id_raw:
        raise _credentials_exception()

    try:
        user_id = uuid.UUID(user_id_raw)
        org_id = uuid.UUID(org_id_raw)
    except ValueError:
        raise _credentials_exception()

    user_repo = UserRepository(db)
    user = user_repo.get_by_id(user_id)
    if user is None or not user.is_active:
        raise _credentials_exception()

    membership_repo = MembershipRepository(db)
    membership = membership_repo.get_by_user_and_org(user_id, org_id)
    if membership is None:
        # Membership was revoked/changed since the token was issued.
        raise _credentials_exception()

    # Role claims are only a hint; require a current, enrolled factor for
    # every privileged request.  This also invalidates old privileged tokens
    # immediately after factor reset or role promotion.
    if role_requires_mfa(membership.role.name):
        credential = MfaService(db).get_credential(user_id)
        if (
            credential is None
            or payload.get("mfa_verified") is not True
            or payload.get("mfa_security_version") != credential.security_version
        ):
            raise _credentials_exception()

    context = RequestContext(
        user_id=user_id,
        organization_id=org_id,
        role=membership.role.name,
        membership_id=membership.id,
    )

    if context.role == "TEACHER":
        teacher = TeacherRepository(db).get_by_membership_id(membership.id)
        context.teacher_id = teacher.id if teacher else None
    elif context.role == "STUDENT":
        student = StudentRepository(db).get_by_membership_id(membership.id)
        context.student_id = student.id if student else None

    return context
