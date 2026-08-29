"""Coverage for the management UI's backing API and student profile.

The tests deliberately use the same two-tenant fixture as the rest of the
suite, so the new convenience endpoints cannot quietly bypass tenant scoping.
"""
import pytest

from app.core.security import hash_password
from app.models.enums import RoleName
from app.models.membership import OrganizationMembership
from app.models.role import Role
from app.models.user import User
from app.tests.conftest import DEV_PASSWORD, OrgFixture, auth_headers


def _role(db, name: RoleName) -> Role:
    role = db.query(Role).filter_by(name=name.value).one_or_none()
    if role is None:
        role = Role(name=name.value)
        db.add(role)
        db.flush()
    return role


def _director_token(client, db, org: OrgFixture) -> str:
    user = User(email=f"director@{org.org.slug}.edu", full_name="Test Director", hashed_password=hash_password(DEV_PASSWORD))
    db.add(user)
    db.flush()
    db.add(OrganizationMembership(user_id=user.id, organization_id=org.org.id, role_id=_role(db, RoleName.DIRECTOR).id))
    db.commit()
    return org.login(client, user.email)


def _privileged_member(db, org: OrgFixture, role_name: RoleName, suffix: str) -> OrganizationMembership:
    user = User(
        email=f"{suffix}@{org.org.slug}.edu",
        full_name=f"Target {role_name.value}",
        hashed_password=hash_password(DEV_PASSWORD),
    )
    db.add(user)
    db.flush()
    membership = OrganizationMembership(
        user_id=user.id,
        organization_id=org.org.id,
        role_id=_role(db, role_name).id,
    )
    db.add(membership)
    db.commit()
    db.refresh(membership)
    return membership


def test_director_can_manage_current_organization_only(client, db, org_a: OrgFixture, org_b: OrgFixture):
    token = _director_token(client, db, org_a)
    headers = auth_headers(token)

    overview = client.get("/api/v1/management/overview", headers=headers)
    assert overview.status_code == 200
    assert overview.json()["organization"]["id"] == str(org_a.org.id)

    member = client.post(
        "/api/v1/management/members",
        headers=headers,
        json={"full_name": "New Student", "email": "new-student@org-a.edu", "password": "Practice123!", "role": "STUDENT"},
    )
    assert member.status_code == 201, member.text
    assert member.json()["role"] == "STUDENT"
    assert member.json()["profile_id"]

    # The caller's tenant is derived from the token.  There is no request
    # field that can redirect this create to org_b.
    groups = client.post(
        "/api/v1/management/groups",
        headers=headers,
        json={"name": "ORG-A-G2", "teacher_ids": [str(org_a.teacher.id)]},
    )
    assert groups.status_code == 201, groups.text
    assert groups.json()["teacher_ids"] == [str(org_a.teacher.id)]
    assert str(org_b.teacher.id) not in groups.json()["teacher_ids"]


def test_student_profile_and_teacher_roster_actions(client, db, org_a: OrgFixture):
    student_token = org_a.student_token(client)
    profile = client.get("/api/v1/profile", headers=auth_headers(student_token))
    assert profile.status_code == 200
    assert profile.json()["student_id"] == str(org_a.student.id)

    update = client.patch("/api/v1/profile", headers=auth_headers(student_token), json={"full_name": "Updated Student"})
    assert update.status_code == 200
    assert update.json()["full_name"] == "Updated Student"

    teacher_token = org_a.teacher_token(client)
    available = client.get(f"/api/v1/groups/{org_a.group.id}/available-students", headers=auth_headers(teacher_token))
    assert available.status_code == 200
    assert str(org_a.student.id) in {student["id"] for student in available.json()}

    add = client.post(f"/api/v1/groups/{org_a.group.id}/students", headers=auth_headers(teacher_token), json={"student_id": str(org_a.student.id)})
    assert add.status_code == 201
    available_after = client.get(f"/api/v1/groups/{org_a.group.id}/available-students", headers=auth_headers(teacher_token))
    assert str(org_a.student.id) not in {student["id"] for student in available_after.json()}


@pytest.mark.parametrize("target_role", [RoleName.DIRECTOR, RoleName.SUPER_ADMIN])
@pytest.mark.parametrize(
    ("payload", "description"),
    [
        ({"full_name": "Escalated Name"}, "change identity"),
        ({"is_active": False}, "deactivate"),
        ({"role": "TEACHER"}, "demote or change role"),
    ],
)
def test_director_cannot_update_privileged_member(
    client,
    db,
    org_a: OrgFixture,
    target_role: RoleName,
    payload: dict,
    description: str,
):
    director_token = _director_token(client, db, org_a)
    target = _privileged_member(db, org_a, target_role, f"target-{target_role.value.lower()}")

    response = client.patch(
        f"/api/v1/management/members/{target.id}",
        headers=auth_headers(director_token),
        json=payload,
    )

    assert response.status_code == 403, f"Director must not {description} for {target_role.value}"
    db.refresh(target)
    assert target.role.name == target_role.value
    assert target.is_active is True
    assert target.user.full_name == f"Target {target_role.value}"


@pytest.mark.parametrize("target_role", [RoleName.DIRECTOR, RoleName.SUPER_ADMIN])
@pytest.mark.parametrize("action", ["invite", "password-reset"])
def test_director_cannot_issue_access_link_for_privileged_member(
    client,
    db,
    org_a: OrgFixture,
    target_role: RoleName,
    action: str,
):
    director_token = _director_token(client, db, org_a)
    target = _privileged_member(db, org_a, target_role, f"link-{target_role.value.lower()}-{action}")

    response = client.post(
        f"/api/v1/management/members/{target.id}/{action}",
        headers=auth_headers(director_token),
    )

    assert response.status_code == 403


@pytest.mark.parametrize("role", ["DIRECTOR", "SUPER_ADMIN"])
def test_director_cannot_create_privileged_member(client, db, org_a: OrgFixture, role: str):
    director_token = _director_token(client, db, org_a)
    response = client.post(
        "/api/v1/management/members",
        headers=auth_headers(director_token),
        json={
            "full_name": f"New {role}",
            "email": f"new-{role.lower()}@org-a.edu",
            "password": DEV_PASSWORD,
            "role": role,
        },
    )
    assert response.status_code == 403


def test_super_admin_can_manage_privileged_member(client, db, org_a: OrgFixture):
    super_admin = _privileged_member(db, org_a, RoleName.SUPER_ADMIN, "actor-super-admin")
    target = _privileged_member(db, org_a, RoleName.DIRECTOR, "managed-director")
    token = org_a.login(client, super_admin.user.email)

    update = client.patch(
        f"/api/v1/management/members/{target.id}",
        headers=auth_headers(token),
        json={"full_name": "Managed Director"},
    )
    invite = client.post(
        f"/api/v1/management/members/{target.id}/invite",
        headers=auth_headers(token),
    )
    reset = client.post(
        f"/api/v1/management/members/{target.id}/password-reset",
        headers=auth_headers(token),
    )

    assert update.status_code == 200
    assert invite.status_code == 200
    assert reset.status_code == 200
