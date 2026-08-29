"""TOTP MFA lifecycle.

Only a short-lived, HttpOnly-bound challenge may turn a successful password
check into a session.  This service intentionally contains no endpoint that
turns a recovery approval into an access token: every recovery ends at fresh
TOTP enrollment.
"""
import base64
import hashlib
import hmac
import io
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal, NoReturn
from urllib.parse import quote

import qrcode  # type: ignore[import-untyped]
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.observability.metrics import metrics
from app.models.enums import AuditEventType, RoleName
from app.models.membership import OrganizationMembership
from app.models.mfa_challenge import MfaChallenge
from app.models.mfa_credential import MfaCredential
from app.models.mfa_recovery_code import MfaRecoveryCode
from app.models.user import User
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.services.audit_service import AuditService

MFA_REQUIRED_ROLES = {RoleName.DIRECTOR.value, RoleName.SUPER_ADMIN.value}
VERIFY = "VERIFY"
ENROLL = "ENROLL"
PEER_RECOVERY = "PEER_RECOVERY"
BREAK_GLASS_ENROLL = "BREAK_GLASS_ENROLL"


def role_requires_mfa(role: str) -> bool:
    return role in MFA_REQUIRED_ROLES


@dataclass(frozen=True)
class CreatedChallenge:
    challenge: MfaChallenge
    cookie_value: str
    status: Literal["MFA_REQUIRED", "MFA_ENROLLMENT_REQUIRED"]


class MfaService:
    def __init__(self, db: Session):
        self.db = db
        self.audit = AuditService(db)
        self.refresh_tokens = RefreshTokenRepository(db)

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _digest(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _recovery_digest(value: str) -> str:
        normalized = "".join(char for char in value.upper() if char.isalnum())
        return hmac.new(settings.MFA_RECOVERY_CODE_PEPPER.encode("utf-8"), normalized.encode("utf-8"), hashlib.sha256).hexdigest()

    @staticmethod
    def _fernet() -> Fernet:
        try:
            return Fernet(settings.MFA_TOTP_ENCRYPTION_KEY.encode("ascii"))
        except (ValueError, TypeError) as exc:
            raise RuntimeError("MFA_TOTP_ENCRYPTION_KEY is not a valid Fernet key") from exc

    def _encrypt(self, value: str) -> str:
        return self._fernet().encrypt(value.encode("utf-8")).decode("ascii")

    def _decrypt(self, value: str) -> str:
        try:
            return self._fernet().decrypt(value.encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeDecodeError) as exc:
            raise RuntimeError("Stored MFA credential cannot be decrypted") from exc

    @staticmethod
    def _new_secret() -> str:
        # RFC 6238-compatible Base32 without padding.
        return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")

    @staticmethod
    def _totp_counter(at: datetime | None = None) -> int:
        instant = at or datetime.now(timezone.utc)
        return int(instant.timestamp()) // 30

    @staticmethod
    def _totp(secret: str, counter: int) -> str:
        padded = secret + "=" * (-len(secret) % 8)
        key = base64.b32decode(padded, casefold=True)
        message = counter.to_bytes(8, "big")
        digest = hmac.new(key, message, hashlib.sha1).digest()
        offset = digest[-1] & 0x0F
        binary = ((digest[offset] & 0x7F) << 24) | (digest[offset + 1] << 16) | (digest[offset + 2] << 8) | digest[offset + 3]
        return f"{binary % 1_000_000:06d}"

    def _matching_counter(self, secret: str, code: str) -> int | None:
        normalized = "".join(char for char in code if char.isdigit())
        if len(normalized) != 6:
            return None
        current = self._totp_counter()
        for counter in (current - 1, current, current + 1):
            if hmac.compare_digest(self._totp(secret, counter), normalized):
                return counter
        return None

    @staticmethod
    def _new_recovery_code() -> str:
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        raw = "".join(secrets.choice(alphabet) for _ in range(12))
        return "-".join((raw[:4], raw[4:8], raw[8:]))

    def get_credential(self, user_id: uuid.UUID) -> MfaCredential | None:
        return self.db.scalar(select(MfaCredential).where(MfaCredential.user_id == user_id))

    def create_challenge(
        self,
        membership: OrganizationMembership,
        *,
        purpose: str | None = None,
        invalidate_previous: bool = True,
    ) -> CreatedChallenge:
        if not membership.is_active or not role_requires_mfa(membership.role.name):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="MFA is not available for this membership")
        user = self.db.get(User, membership.user_id)
        if user is None or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="MFA is not available for this user")
        if invalidate_previous:
            existing = self.db.scalars(
                select(MfaChallenge).where(
                    MfaChallenge.user_id == membership.user_id,
                    MfaChallenge.organization_id == membership.organization_id,
                    MfaChallenge.consumed_at.is_(None),
                )
            )
            for challenge in existing:
                challenge.consumed_at = self._now()
        credential = self.get_credential(membership.user_id)
        selected_purpose = purpose or (VERIFY if credential else ENROLL)
        cookie_value = secrets.token_urlsafe(48)
        challenge = MfaChallenge(
            user_id=membership.user_id,
            organization_id=membership.organization_id,
            membership_id=membership.id,
            purpose=selected_purpose,
            cookie_hash=self._digest(cookie_value),
            expires_at=self._now() + timedelta(minutes=settings.MFA_CHALLENGE_EXPIRE_MINUTES),
        )
        self.db.add(challenge)
        self.db.flush()
        self.audit.record(
            organization_id=membership.organization_id,
            actor_user_id=membership.user_id,
            event_type=AuditEventType.MFA_CHALLENGE_CREATED,
            entity_type="mfa_challenge",
            entity_id=challenge.id,
            metadata={"purpose": selected_purpose},
        )
        result_status = "MFA_ENROLLMENT_REQUIRED" if selected_purpose in {ENROLL, BREAK_GLASS_ENROLL} else "MFA_REQUIRED"
        metrics.observe_mfa("enrollment" if result_status == "MFA_ENROLLMENT_REQUIRED" else "challenge", "success")
        return CreatedChallenge(challenge, cookie_value, result_status)

    def _owned_challenge(self, challenge_id: uuid.UUID, cookie_value: str | None) -> MfaChallenge:
        challenge = self.db.get(MfaChallenge, challenge_id)
        if challenge is None or not cookie_value or not hmac.compare_digest(challenge.cookie_hash, self._digest(cookie_value)):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="MFA challenge is invalid")
        if challenge.consumed_at is not None or challenge.expires_at <= self._now():
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="MFA challenge has expired")
        membership = self.db.get(OrganizationMembership, challenge.membership_id)
        if membership is None or not membership.is_active or not role_requires_mfa(membership.role.name):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="MFA challenge is no longer valid")
        user = self.db.get(User, challenge.user_id)
        if user is None or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="MFA challenge is no longer valid")
        return challenge

    def _record_code_failure(self, challenge: MfaChallenge, action: str) -> NoReturn:
        challenge.attempts += 1
        if challenge.attempts >= settings.MFA_MAX_ATTEMPTS:
            challenge.consumed_at = self._now()
        self.db.commit()
        metrics.observe_mfa(action, "failure")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication code")

    def start_enrollment(self, challenge_id: uuid.UUID, cookie_value: str | None) -> tuple[MfaChallenge, str, str]:
        challenge = self._owned_challenge(challenge_id, cookie_value)
        if challenge.purpose not in {ENROLL, BREAK_GLASS_ENROLL}:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This challenge is not an enrollment challenge")
        if challenge.pending_secret_encrypted is None:
            challenge.pending_secret_encrypted = self._encrypt(self._new_secret())
            self.db.commit()
        secret = self._decrypt(challenge.pending_secret_encrypted)
        issuer = quote(settings.PROJECT_NAME, safe="")
        label = quote(f"{settings.PROJECT_NAME}:{challenge.user_id}", safe="")
        otpauth_uri = f"otpauth://totp/{label}?secret={secret}&issuer={issuer}&algorithm=SHA1&digits=6&period=30"
        image = qrcode.make(otpauth_uri)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        data_url = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
        return challenge, secret, data_url

    def complete_enrollment(self, challenge_id: uuid.UUID, cookie_value: str | None, code: str) -> tuple[str, str, list[str]]:
        challenge = self._owned_challenge(challenge_id, cookie_value)
        if challenge.purpose not in {ENROLL, BREAK_GLASS_ENROLL} or not challenge.pending_secret_encrypted:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Start MFA enrollment before confirming it")
        secret = self._decrypt(challenge.pending_secret_encrypted)
        counter = self._matching_counter(secret, code)
        if counter is None:
            self._record_code_failure(challenge, "break_glass" if challenge.purpose == BREAK_GLASS_ENROLL else "enrollment")
        credential = self.get_credential(challenge.user_id)
        if credential is None:
            credential = MfaCredential(user_id=challenge.user_id, secret_encrypted=self._encrypt(secret), enabled_at=self._now(), last_totp_counter=counter)
            self.db.add(credential)
            self.db.flush()
        else:
            credential.secret_encrypted = self._encrypt(secret)
            credential.enabled_at = self._now()
            credential.security_version += 1
            credential.last_totp_counter = counter
            for old in self.db.scalars(select(MfaRecoveryCode).where(MfaRecoveryCode.credential_id == credential.id)):
                self.db.delete(old)
            self.refresh_tokens.revoke_all_for_user(challenge.user_id)
        recovery_codes = [self._new_recovery_code() for _ in range(10)]
        for recovery_code in recovery_codes:
            self.db.add(MfaRecoveryCode(credential_id=credential.id, code_hash=self._recovery_digest(recovery_code)))
        challenge.consumed_at = self._now()
        self.audit.record(
            organization_id=challenge.organization_id,
            actor_user_id=challenge.user_id,
            event_type=AuditEventType.MFA_ENROLLED,
            entity_type="mfa_credential",
            entity_id=credential.id,
            metadata={"purpose": challenge.purpose},
        )
        access, refresh = self._issue_session(challenge, credential)
        self.db.commit()
        metrics.observe_mfa("break_glass" if challenge.purpose == BREAK_GLASS_ENROLL else "enrollment", "success")
        return access, refresh, recovery_codes

    def verify(self, challenge_id: uuid.UUID, cookie_value: str | None, code: str) -> tuple[str, str]:
        challenge = self._owned_challenge(challenge_id, cookie_value)
        if challenge.purpose != VERIFY:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This challenge requires MFA enrollment")
        credential = self.get_credential(challenge.user_id)
        if credential is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="MFA credential is not enrolled")
        counter = self._matching_counter(self._decrypt(credential.secret_encrypted), code)
        if counter is None or (credential.last_totp_counter is not None and counter <= credential.last_totp_counter):
            self._record_code_failure(challenge, "challenge")
        credential.last_totp_counter = counter
        challenge.consumed_at = self._now()
        self.audit.record(
            organization_id=challenge.organization_id,
            actor_user_id=challenge.user_id,
            event_type=AuditEventType.MFA_VERIFIED,
            entity_type="mfa_challenge",
            entity_id=challenge.id,
        )
        access, refresh = self._issue_session(challenge, credential)
        self.db.commit()
        metrics.observe_mfa("challenge", "success")
        return access, refresh

    def use_recovery_code(self, challenge_id: uuid.UUID, cookie_value: str | None, recovery_code: str) -> CreatedChallenge:
        challenge = self._owned_challenge(challenge_id, cookie_value)
        if challenge.purpose != VERIFY:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Recovery is not available for this challenge")
        credential = self.get_credential(challenge.user_id)
        if credential is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="MFA credential is not enrolled")
        expected = self._recovery_digest(recovery_code)
        records = list(self.db.scalars(select(MfaRecoveryCode).where(MfaRecoveryCode.credential_id == credential.id, MfaRecoveryCode.used_at.is_(None))))
        matching = next((record for record in records if hmac.compare_digest(record.code_hash, expected)), None)
        if matching is None:
            self._record_code_failure(challenge, "recovery")
        matching.used_at = self._now()
        self._reset_factor(challenge, AuditEventType.MFA_RECOVERY_USED)
        membership = self.db.get(OrganizationMembership, challenge.membership_id)
        if membership is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="MFA challenge is no longer valid")
        replacement = self.create_challenge(membership, purpose=ENROLL, invalidate_previous=False)
        self.db.commit()
        metrics.observe_mfa("recovery", "success")
        return replacement

    def request_peer_recovery(self, challenge_id: uuid.UUID, cookie_value: str | None) -> MfaChallenge:
        challenge = self._owned_challenge(challenge_id, cookie_value)
        membership = self.db.get(OrganizationMembership, challenge.membership_id)
        if membership is None or challenge.purpose != VERIFY or membership.role.name != RoleName.SUPER_ADMIN.value:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Peer recovery is available only to Super Admins")
        challenge.purpose = PEER_RECOVERY
        self.audit.record(
            organization_id=challenge.organization_id,
            actor_user_id=challenge.user_id,
            event_type=AuditEventType.MFA_RECOVERY_REQUESTED,
            entity_type="mfa_challenge",
            entity_id=challenge.id,
        )
        self.db.commit()
        metrics.observe_mfa("peer_recovery", "success")
        return challenge

    def peer_recovery_status(self, challenge_id: uuid.UUID, cookie_value: str | None) -> MfaChallenge:
        return self._owned_challenge(challenge_id, cookie_value)

    def list_peer_recovery_requests(self, organization_id: uuid.UUID) -> list[MfaChallenge]:
        return list(self.db.scalars(select(MfaChallenge).where(
            MfaChallenge.organization_id == organization_id,
            MfaChallenge.purpose == PEER_RECOVERY,
            MfaChallenge.consumed_at.is_(None),
            MfaChallenge.expires_at > self._now(),
        ).order_by(MfaChallenge.created_at)))

    def approve_peer_recovery(self, challenge_id: uuid.UUID, organization_id: uuid.UUID, approver_user_id: uuid.UUID) -> None:
        challenge = self.db.get(MfaChallenge, challenge_id)
        if challenge is None or challenge.organization_id != organization_id or challenge.purpose != PEER_RECOVERY or challenge.expires_at <= self._now() or challenge.consumed_at is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MFA recovery request was not found")
        if challenge.user_id == approver_user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="A Super Admin cannot approve their own recovery")
        challenge.approved_at = self._now()
        challenge.approved_by_user_id = approver_user_id
        self.audit.record(
            organization_id=organization_id,
            actor_user_id=approver_user_id,
            event_type=AuditEventType.MFA_RECOVERY_APPROVED,
            entity_type="mfa_challenge",
            entity_id=challenge.id,
            metadata={"target_user_id": str(challenge.user_id)},
        )
        self.db.commit()

    def complete_peer_recovery(self, challenge_id: uuid.UUID, cookie_value: str | None) -> CreatedChallenge:
        challenge = self._owned_challenge(challenge_id, cookie_value)
        if challenge.purpose != PEER_RECOVERY or challenge.approved_at is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This recovery request has not been approved")
        self._reset_factor(challenge, AuditEventType.MFA_RESET)
        membership = self.db.get(OrganizationMembership, challenge.membership_id)
        if membership is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="MFA challenge is no longer valid")
        replacement = self.create_challenge(membership, purpose=ENROLL, invalidate_previous=False)
        self.db.commit()
        metrics.observe_mfa("peer_recovery", "success")
        return replacement

    def _reset_factor(self, challenge: MfaChallenge, event: AuditEventType) -> None:
        credential = self.get_credential(challenge.user_id)
        if credential is not None:
            self.db.delete(credential)
        challenge.consumed_at = self._now()
        self.refresh_tokens.revoke_all_for_user(challenge.user_id)
        self.audit.record(
            organization_id=challenge.organization_id,
            actor_user_id=challenge.user_id,
            event_type=event,
            entity_type="mfa_credential",
            entity_id=credential.id if credential else None,
        )

    def revoke_pending_for_user(self, user_id: uuid.UUID) -> None:
        for challenge in self.db.scalars(select(MfaChallenge).where(MfaChallenge.user_id == user_id, MfaChallenge.consumed_at.is_(None))):
            challenge.consumed_at = self._now()
        self.db.flush()

    def create_break_glass_challenge(self, membership: OrganizationMembership) -> tuple[MfaChallenge, str]:
        """Trusted operational helper; only the offline-custodian script calls it."""
        credential = self.get_credential(membership.user_id)
        if credential is not None:
            self.db.delete(credential)
        self.refresh_tokens.revoke_all_for_user(membership.user_id)
        self.revoke_pending_for_user(membership.user_id)
        self.audit.record(
            organization_id=membership.organization_id,
            actor_user_id=None,
            event_type=AuditEventType.MFA_BREAK_GLASS_STARTED,
            entity_type="mfa_credential",
            entity_id=credential.id if credential else None,
            metadata={"target_user_id": str(membership.user_id)},
        )
        created = self.create_challenge(membership, purpose=BREAK_GLASS_ENROLL, invalidate_previous=False)
        code = secrets.token_urlsafe(32)
        created.challenge.recovery_code_hash = self._recovery_digest(code)
        self.db.commit()
        return created.challenge, code

    def start_break_glass(self, challenge_id: uuid.UUID, enrollment_code: str) -> CreatedChallenge:
        challenge = self.db.get(MfaChallenge, challenge_id)
        if challenge is None or challenge.purpose != BREAK_GLASS_ENROLL or challenge.consumed_at is not None or challenge.expires_at <= self._now():
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Break-glass enrollment is invalid")
        if not challenge.recovery_code_hash or not hmac.compare_digest(challenge.recovery_code_hash, self._recovery_digest(enrollment_code)):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Break-glass enrollment is invalid")
        # A newly bound browser gets a distinct challenge cookie; the supplied
        # offline code is consumed and can never mint a token.
        challenge.consumed_at = self._now()
        membership = self.db.get(OrganizationMembership, challenge.membership_id)
        if membership is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Break-glass enrollment is invalid")
        created = self.create_challenge(membership, purpose=BREAK_GLASS_ENROLL, invalidate_previous=False)
        self.db.commit()
        return created

    def _issue_session(self, challenge: MfaChallenge, credential: MfaCredential) -> tuple[str, str]:
        # Import here to avoid a module cycle: AuthService creates MFA
        # challenges during password / organization-switch processing.
        from app.services.auth_service import AuthService

        membership = self.db.get(OrganizationMembership, challenge.membership_id)
        if membership is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="MFA challenge is no longer valid")
        access, refresh = AuthService(self.db)._issue_tokens(
            challenge.user_id,
            challenge.organization_id,
            membership.role.name,
            mfa_verified=True,
            mfa_security_version=credential.security_version,
        )
        self.audit.record(
            organization_id=challenge.organization_id,
            actor_user_id=challenge.user_id,
            event_type=AuditEventType.LOGIN,
            entity_type="user",
            entity_id=challenge.user_id,
            metadata={"mfa": True},
        )
        return access, refresh
