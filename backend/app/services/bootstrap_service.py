"""Atomic first-tenant provisioning for the private bootstrap CLI only."""
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.enums import AuditEventType, RoleName
from app.models.membership import OrganizationMembership
from app.models.organization import Organization
from app.models.role import Role
from app.models.user import User
from app.services.audit_service import AuditService


class BootstrapIdentity(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, hide_input_in_errors=True)

    organization_name: str = Field(min_length=2, max_length=255)
    organization_slug: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    admin_email: EmailStr = Field(max_length=255)
    admin_full_name: str = Field(min_length=2, max_length=255)


class BootstrapConflict(ValueError):
    pass


@dataclass(frozen=True)
class BootstrapResult:
    created: bool
    organization_id: UUID
    user_id: UUID


def bootstrap(db: Session, identity: BootstrapIdentity, password_provider: Callable[[], str]) -> BootstrapResult:
    """Own one transaction; never adopt, promote, reactivate or reset identities.

    Table locks also serialize non-cooperating inserts from normal application
    writers. Run before admitting traffic. A repeat does not request a password.
    """
    with db.begin():
        db.execute(text("SET LOCAL lock_timeout = '5s'"))
        db.execute(text("LOCK TABLE roles, organizations, users, organization_memberships IN SHARE ROW EXCLUSIVE MODE"))
        organization = db.scalar(select(Organization).where(Organization.slug == identity.organization_slug))
        # Existing mixed-case identities must not be duplicated or adopted.
        users = list(db.scalars(select(User).where(func.lower(User.email) == str(identity.admin_email).lower())))
        user = users[0] if len(users) == 1 else None
        membership = None
        if organization is not None and user is not None:
            membership = db.scalar(select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization.id,
                OrganizationMembership.user_id == user.id,
            ))
        if (
            organization is not None and user is not None and membership is not None
            and organization.name == identity.organization_name
            and user.email == str(identity.admin_email) and user.full_name == identity.admin_full_name
            and user.is_active and membership.is_active and membership.role.name == RoleName.SUPER_ADMIN.value
        ):
            return BootstrapResult(False, organization.id, user.id)
        if (
            db.scalar(select(User.id).limit(1)) is not None
            or db.scalar(select(Organization.id).limit(1)) is not None
            or db.scalar(select(OrganizationMembership.id).limit(1)) is not None
        ):
            raise BootstrapConflict(
                "Database contains existing identities or conflicting organization/user/membership data. "
                "Use the exact original identity for a no-op, or the authenticated administration/recovery workflow. "
                "This command cannot change passwords, roles, MFA or active status."
            )

        # Validate and hash with the application's unchanged password policy.
        # Do this before any insert; no plaintext enters a SQL parameter.
        password_hash = hash_password(password_provider())
        roles = {role.name: role for role in db.scalars(select(Role))}
        for name in RoleName:
            if name.value not in roles:
                roles[name.value] = Role(name=name.value)
                db.add(roles[name.value])
        organization = Organization(name=identity.organization_name, slug=identity.organization_slug)
        user = User(
            email=str(identity.admin_email), full_name=identity.admin_full_name,
            hashed_password=password_hash, is_active=True,
        )
        db.add_all([organization, user])
        db.flush()
        membership = OrganizationMembership(
            user_id=user.id, organization_id=organization.id,
            role_id=roles[RoleName.SUPER_ADMIN.value].id, is_active=True,
        )
        db.add(membership)
        db.flush()
        audit = AuditService(db)
        for event_type, entity_type, entity_id in (
            (AuditEventType.ORGANIZATION_CREATED, "organization", organization.id),
            (AuditEventType.MEMBERSHIP_CREATED, "membership", membership.id),
        ):
            audit.record(
                organization_id=organization.id, actor_user_id=user.id,
                event_type=event_type, entity_type=entity_type, entity_id=entity_id,
                metadata={"bootstrap": True},
            )
        # No MFA credential, challenge, recovery code or login session is made.
        return BootstrapResult(True, organization.id, user.id)
