from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models.audit_log import AuditLog
from app.models.enums import AuditEventType, RoleName
from app.models.membership import OrganizationMembership
from app.models.role import Role
from app.models.user import User
from app.schemas.management import CreateMemberRequest
from app.services.audit_service import AuditService
from app.services.management_service import ManagementService
from app.tests.conftest import DEV_PASSWORD, OrgFixture, auth_headers


def _super_admin(org: OrgFixture, suffix: str):
    role = org.db.scalar(select(Role).where(Role.name == RoleName.SUPER_ADMIN.value))
    if role is None:
        role = Role(name=RoleName.SUPER_ADMIN.value)
        org.db.add(role)
        org.db.flush()
    user = User(
        email=f"super-{suffix}@{org.org.slug}.edu",
        hashed_password=hash_password(DEV_PASSWORD),
        full_name=f"Super {suffix}",
    )
    org.db.add(user)
    org.db.flush()
    org.db.add(OrganizationMembership(user_id=user.id, organization_id=org.org.id, role_id=role.id))
    org.db.commit()
    return user


def test_audit_chain_detects_metadata_tampering_and_drops_secrets(db, org_a: OrgFixture):
    service = AuditService(db)
    first = service.record(
        organization_id=org_a.org.id,
        actor_user_id=org_a.teacher_user.id,
        event_type=AuditEventType.MEMBERSHIP_CREATED,
        entity_type="membership",
        entity_id=org_a.teacher.membership_id,
        metadata={"password": "never-store", "email": "person@example.edu", "filename": "secret.png", "size_bytes": 42},
    )
    service.record(
        organization_id=org_a.org.id,
        actor_user_id=org_a.teacher_user.id,
        event_type=AuditEventType.GROUP_CREATED,
        entity_type="group",
        entity_id=org_a.group.id,
    )
    db.commit()

    assert first.event_metadata == {"size_bytes": 42}
    assert service.verify(org_a.org.id).valid

    first.event_metadata = {"size_bytes": 43}
    db.commit()
    result = service.verify(org_a.org.id)
    assert not result.valid
    assert result.first_invalid_sequence == first.sequence


def test_critical_membership_mutation_rolls_back_when_audit_append_fails(db, org_a: OrgFixture):
    service = ManagementService(db)
    service.audit.record = Mock(side_effect=RuntimeError("audit storage failure"))
    with pytest.raises(RuntimeError, match="audit storage failure"):
        service.create_member(
            org_a.org.id,
            CreateMemberRequest(full_name="New Member", email="new-member@example.edu", password="SafePassword123!", role=RoleName.STUDENT),
            RoleName.SUPER_ADMIN.value,
            org_a.teacher_user.id,
        )
    db.rollback()
    assert db.scalar(select(User).where(User.email == "new-member@example.edu")) is None


def test_audit_read_api_is_tenant_scoped_paginated_and_append_only(client, db, org_a: OrgFixture, org_b: OrgFixture):
    admin_a = _super_admin(org_a, "a")
    admin_b = _super_admin(org_b, "b")
    service = AuditService(db)
    service.record(organization_id=org_a.org.id, actor_user_id=admin_a.id, event_type=AuditEventType.REPORT_SUBMITTED, entity_type="report", entity_id=org_a.group.id)
    service.record(organization_id=org_b.org.id, actor_user_id=admin_b.id, event_type=AuditEventType.REPORT_APPROVED, entity_type="report", entity_id=org_b.group.id)
    db.commit()

    token_a = org_a.login(client, admin_a.email)
    token_b = org_b.login(client, admin_b.email)
    response_a = client.get(
        f"/api/v1/audit-events?offset=0&limit=1&action=REPORT_SUBMITTED&actor_id={admin_a.id}&target_type=report&target_id={org_a.group.id}",
        headers=auth_headers(token_a),
    )
    assert response_a.status_code == 200
    assert response_a.headers["X-Total-Count"] == "1"
    assert [row["action"] for row in response_a.json()] == ["REPORT_SUBMITTED"]

    # A Super Admin authenticated in organization B has no way to supply an
    # organization A selector and cannot see its row even knowing its UUID.
    response_b = client.get("/api/v1/audit-events?offset=0&limit=50", headers=auth_headers(token_b))
    assert response_b.status_code == 200
    assert all(row["target_id"] != str(org_a.group.id) for row in response_b.json())
    assert any(row["action"] == "REPORT_APPROVED" for row in response_b.json())
    assert client.get("/api/v1/audit-events", headers=auth_headers(org_a.teacher_token(client))).status_code == 403
    assert client.delete("/api/v1/audit-events", headers=auth_headers(token_a)).status_code == 405
    assert client.put("/api/v1/audit-events", headers=auth_headers(token_a)).status_code == 405


def test_audit_retention_checkpoint_preserves_retained_chain(db, org_a: OrgFixture, monkeypatch):
    import app.services.audit_service as audit_module

    old_time = datetime.now(UTC) - timedelta(days=10)
    monkeypatch.setattr(audit_module, "utcnow", lambda: old_time)
    service = AuditService(db)
    service.record(organization_id=org_a.org.id, actor_user_id=org_a.teacher_user.id, event_type=AuditEventType.GROUP_CREATED, entity_type="group", entity_id=org_a.group.id)
    service.record(organization_id=org_a.org.id, actor_user_id=org_a.teacher_user.id, event_type=AuditEventType.STUDENT_UPDATED, entity_type="student", entity_id=org_a.student.id)
    db.commit()

    monkeypatch.setattr(audit_module, "utcnow", lambda: datetime.now(UTC))
    service.record(organization_id=org_a.org.id, actor_user_id=org_a.teacher_user.id, event_type=AuditEventType.REPORT_SUBMITTED, entity_type="report", entity_id=org_a.group.id)
    db.commit()
    assert service.cleanup_expired(retention_days=1) == 2
    assert service.verify(org_a.org.id).valid
    retained = db.scalars(select(AuditLog).where(AuditLog.organization_id == org_a.org.id).order_by(AuditLog.sequence)).all()
    assert retained[0].sequence == 3
    assert any(event.event_type == AuditEventType.AUDIT_RETENTION_CHECKPOINT for event in retained)
