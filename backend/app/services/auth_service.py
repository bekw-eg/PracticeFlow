import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.models.enums import AuditEventType
from app.models.refresh_token import RefreshToken
from app.repositories.membership_repository import MembershipRepository
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository
from app.services.audit_service import AuditService
from app.services.mfa_service import CreatedChallenge, MfaService, role_requires_mfa


@dataclass(frozen=True)
class AuthFlowResult:
    access_token: str | None = None
    refresh_token: str | None = None
    mfa_challenge: CreatedChallenge | None = None


class AuthService:
    def __init__(self, db: Session):
        self.db = db
        self.user_repo = UserRepository(db)
        self.membership_repo = MembershipRepository(db)
        self.org_repo = OrganizationRepository(db)
        self.refresh_repo = RefreshTokenRepository(db)
        self.audit = AuditService(db)

    def login(self, email: str, password: str, organization_slug: str) -> AuthFlowResult:
        invalid = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

        organization = self.org_repo.get_by_slug(organization_slug)
        if organization is None:
            raise invalid

        user = self.user_repo.get_by_email(email)
        if user is None or not user.is_active:
            raise invalid
        if not verify_password(password, user.hashed_password):
            raise invalid

        membership = self.membership_repo.get_by_user_and_org(user.id, organization.id)
        if membership is None:
            # User exists but has no membership in THIS organization — same
            # generic error as bad credentials, to avoid leaking which orgs
            # a given email is a member of.
            raise invalid

        if role_requires_mfa(membership.role.name):
            challenge = MfaService(self.db).create_challenge(membership)
            self.db.commit()
            return AuthFlowResult(mfa_challenge=challenge)

        access_token, refresh_token = self._issue_tokens(user.id, membership.organization_id, membership.role.name)

        self.audit.record(
            organization_id=organization.id,
            actor_user_id=user.id,
            event_type=AuditEventType.LOGIN,
            entity_type="user",
            entity_id=user.id,
        )
        self.db.commit()
        return AuthFlowResult(access_token=access_token, refresh_token=refresh_token)

    def refresh(self, refresh_token: str) -> tuple[str, str]:
        invalid = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

        try:
            payload = decode_token(refresh_token)
        except Exception:
            raise invalid

        if payload.get("type") != "refresh":
            raise invalid

        jti = payload.get("jti")
        stored = self.refresh_repo.get_by_jti(jti) if jti else None
        if stored is None or stored.revoked:
            raise invalid
        if stored.expires_at < datetime.now(timezone.utc):
            raise invalid

        user = self.user_repo.get_by_id(stored.user_id)
        if user is None or not user.is_active:
            raise invalid

        # Refresh is bound to the organization selected at login.  If that
        # membership has been revoked, never switch the session to some other
        # organization implicitly.
        token_org_id = stored.organization_id or payload.get("org_id")
        try:
            organization_id = uuid.UUID(str(token_org_id))
        except (TypeError, ValueError):
            raise invalid
        membership = self.membership_repo.get_by_user_and_org(user.id, organization_id)
        if membership is None:
            self.refresh_repo.revoke(stored)
            self.db.commit()
            raise invalid

        if role_requires_mfa(membership.role.name):
            credential = MfaService(self.db).get_credential(user.id)
            if (
                credential is None
                or not stored.mfa_verified
                or stored.mfa_security_version != credential.security_version
            ):
                self.refresh_repo.revoke(stored)
                self.db.commit()
                raise invalid
            mfa_verified = True
            mfa_security_version = credential.security_version
        else:
            mfa_verified = False
            mfa_security_version = None

        self.refresh_repo.revoke(stored)
        new_access, new_refresh = self._issue_tokens(
            user.id,
            membership.organization_id,
            membership.role.name,
            mfa_verified=mfa_verified,
            mfa_security_version=mfa_security_version,
        )
        self.db.commit()
        return new_access, new_refresh

    def list_organizations(self, user_id: uuid.UUID, offset: int = 0, limit: int | None = None) -> list:
        return self.membership_repo.list_by_user(user_id, offset, limit)

    def count_organizations(self, user_id: uuid.UUID) -> int:
        return self.membership_repo.count_by_user(user_id)

    def switch_organization(self, user_id: uuid.UUID, organization_id: uuid.UUID) -> AuthFlowResult:
        membership = self.membership_repo.get_by_user_and_org(user_id, organization_id)
        if membership is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organization is not available to this user")
        if role_requires_mfa(membership.role.name):
            challenge = MfaService(self.db).create_challenge(membership)
            self.db.commit()
            return AuthFlowResult(mfa_challenge=challenge)
        access, refresh = self._issue_tokens(user_id, membership.organization_id, membership.role.name)
        self.db.commit()
        return AuthFlowResult(access_token=access, refresh_token=refresh)

    def _issue_tokens(
        self,
        user_id: uuid.UUID,
        organization_id: uuid.UUID,
        role: str,
        *,
        mfa_verified: bool = False,
        mfa_security_version: int | None = None,
    ) -> tuple[str, str]:
        access_token = create_access_token(
            user_id=user_id,
            org_id=organization_id,
            role=role,
            mfa_verified=mfa_verified,
            mfa_security_version=mfa_security_version,
        )
        refresh_token, jti, expires_at = create_refresh_token(
            user_id,
            organization_id,
            mfa_verified=mfa_verified,
            mfa_security_version=mfa_security_version,
        )
        self.refresh_repo.add(
            RefreshToken(
                user_id=user_id,
                organization_id=organization_id,
                jti=jti,
                expires_at=expires_at,
                mfa_verified=mfa_verified,
                mfa_security_version=mfa_security_version,
            )
        )
        return access_token, refresh_token

    def logout(self, refresh_token: str) -> None:
        try:
            payload = decode_token(refresh_token)
        except Exception:
            return
        jti = payload.get("jti")
        if not jti:
            return
        stored = self.refresh_repo.get_by_jti(jti)
        if stored and not stored.revoked:
            self.refresh_repo.revoke(stored)
            self.audit.record(
                organization_id=stored.organization_id,
                actor_user_id=stored.user_id,
                event_type=AuditEventType.LOGOUT,
                entity_type="user",
                entity_id=stored.user_id,
            )
        self.db.commit()
