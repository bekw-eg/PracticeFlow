import hashlib
import secrets
import smtplib
import uuid
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.models.access_link import AccessLink
from app.models.enums import AuditEventType
from app.models.membership import OrganizationMembership
from app.models.organization import Organization
from app.models.user import User
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.services.mfa_service import MfaService
from app.services.audit_service import AuditService


class AccessLinkService:
    def __init__(self, db: Session):
        self.db = db
        self.refresh_tokens = RefreshTokenRepository(db)

    @staticmethod
    def _digest(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def create(
        self, user: User, organization_id: uuid.UUID, purpose: str, *, actor_user_id: uuid.UUID | None = None
    ) -> dict:
        token = secrets.token_urlsafe(32)
        record = AccessLink(
            user_id=user.id,
            organization_id=organization_id,
            purpose=purpose,
            token_hash=self._digest(token),
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        self.db.add(record)
        self.db.flush()
        AuditService(self.db).record(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            event_type=AuditEventType.INVITE_CREATED if purpose == "INVITE" else AuditEventType.PASSWORD_RESET_CREATED,
            entity_type="access_link",
            entity_id=record.id,
            metadata={"purpose": purpose},
        )
        self.db.commit()
        url = f"{settings.FRONTEND_URL}/access?token={token}"
        delivery = self._send_email(user.email, purpose, url)
        return {"purpose": purpose, "access_url": url, "delivery": delivery}

    def complete(self, token: str, password: str) -> None:
        record = self.db.scalar(select(AccessLink).where(AccessLink.token_hash == self._digest(token)))
        if record is None or record.used_at is not None or record.expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This access link is invalid or has expired.")
        user = self.db.get(User, record.user_id)
        user.hashed_password = hash_password(password)
        user.is_active = True
        record.used_at = datetime.now(timezone.utc)
        self.refresh_tokens.revoke_all_for_user(user.id)
        # Password reset never disables a TOTP factor, but it does invalidate
        # any password-authenticated challenge that may be open in a browser.
        MfaService(self.db).revoke_pending_for_user(user.id)
        AuditService(self.db).record(
            organization_id=record.organization_id,
            actor_user_id=user.id,
            event_type=AuditEventType.PASSWORD_RESET_COMPLETED,
            entity_type="access_link",
            entity_id=record.id,
            metadata={"purpose": record.purpose},
        )
        self.db.commit()

    def request_password_reset(self, email: str, organization_slug: str) -> None:
        """Send a reset link only for an active membership, without revealing
        whether an account or organization matched the supplied details.

        The public flow can only deliver a link through configured SMTP.  The
        administrator-only flow remains available when SMTP is intentionally
        disabled, because only an authenticated administrator may receive a
        copyable one-time link.
        """
        if not settings.SMTP_HOST:
            return

        membership = self.db.scalar(
            select(OrganizationMembership)
            .join(OrganizationMembership.user)
            .join(OrganizationMembership.organization)
            .where(
                User.email == email.strip().lower(),
                Organization.slug == organization_slug.strip(),
                User.is_active.is_(True),
                OrganizationMembership.is_active.is_(True),
            )
        )
        if membership is not None:
            # Do not return the result: it contains the bearer token and is
            # intended solely for delivery to the account's existing mailbox.
            self.create(membership.user, membership.organization_id, "PASSWORD_RESET")

    def _send_email(self, recipient: str, purpose: str, url: str) -> str:
        if not settings.SMTP_HOST:
            return "copy_link"
        subject = "Приглашение в PracticeFlow" if purpose == "INVITE" else "Сброс пароля PracticeFlow"
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = settings.SMTP_FROM
        message["To"] = recipient
        message.set_content(f"Откройте ссылку, чтобы продолжить: {url}")
        try:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as smtp:
                smtp.starttls()
                if settings.SMTP_USERNAME:
                    smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD or "")
                smtp.send_message(message)
            return "email"
        except OSError:
            return "copy_link"
