"""Two-custodian, offline Super Admin MFA recovery.

Run only from the private deployment host/container. This command never
creates a login token: it revokes sessions and emits a one-time code that can
only begin fresh TOTP enrollment in the browser.
"""
import argparse
import hashlib
import hmac
import os
import uuid

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.models.enums import RoleName
from app.models.membership import OrganizationMembership
from app.services.mfa_service import MfaService


def _matches(raw_value: str | None, expected_hash: str | None) -> bool:
    if not raw_value or not expected_hash:
        return False
    return hmac.compare_digest(hashlib.sha256(raw_value.encode("utf-8")).hexdigest(), expected_hash.lower())


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a Super Admin MFA re-enrollment challenge after two offline approvals.")
    parser.add_argument("--user-id", required=True, type=uuid.UUID)
    parser.add_argument("--organization-id", required=True, type=uuid.UUID)
    args = parser.parse_args()
    if not _matches(os.environ.get("MFA_BREAK_GLASS_APPROVAL_A"), settings.MFA_BREAK_GLASS_KEY_A_HASH) or not _matches(os.environ.get("MFA_BREAK_GLASS_APPROVAL_B"), settings.MFA_BREAK_GLASS_KEY_B_HASH):
        raise SystemExit("Both independent MFA_BREAK_GLASS_APPROVAL_A/B values must match configured custodian hashes.")

    engine = create_engine(settings.DATABASE_URL)
    with Session(engine) as db:
        membership = db.scalar(select(OrganizationMembership).options(joinedload(OrganizationMembership.role)).where(
            OrganizationMembership.user_id == args.user_id,
            OrganizationMembership.organization_id == args.organization_id,
            OrganizationMembership.is_active.is_(True),
        ))
        if membership is None or membership.role.name != RoleName.SUPER_ADMIN.value:
            raise SystemExit("Target must be an active Super Admin in the selected organization.")
        challenge, enrollment_code = MfaService(db).create_break_glass_challenge(membership)
        print("Break-glass challenge created. Deliver these values through a separate approved secure channel:")
        print(f"challenge_id={challenge.id}")
        print(f"enrollment_code={enrollment_code}")
        print("The recipient must use /api/v1/auth/mfa/break-glass/start and then enroll a fresh TOTP factor. No session was issued.")


if __name__ == "__main__":
    main()
