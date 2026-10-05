"""Coverage for the management UI's backing API and student profile.

The tests deliberately use the same two-tenant fixture as the rest of the
suite, so the new convenience endpoints cannot quietly bypass tenant scoping.
"""
from datetime import date, timedelta

import pytest

from app.core.security import hash_password
from app.models.enums import InternshipStatus, ReportStatus, RoleName
from app.models.group_member import GroupMember
from app.models.internship import Internship
from app.models.membership import OrganizationMembership
from app.models.report import Report
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


def test_director_dashboard_is_tenant_scoped_and_excludes_report_content(client, db, org_a: OrgFixture, org_b: OrgFixture):
    """Directors receive aggregate metadata for their tenant, never documents."""
    today = date.today()
    db.add(GroupMember(group_id=org_a.group.id, student_id=org_a.student.id))
    db.add(GroupMember(group_id=org_b.group.id, student_id=org_b.student.id))
    overdue_internship = Internship(
        organization_id=org_a.org.id,
        group_id=org_a.group.id,
        template_version_id=org_a.template_version.id,
        created_by_teacher_id=org_a.teacher.id,
        title="Organization A overdue internship",
        start_date=today - timedelta(days=20),
        end_date=today - timedelta(days=10),
        deadline=today - timedelta(days=2),
        status=InternshipStatus.PUBLISHED,
    )
    upcoming_internship = Internship(
        organization_id=org_a.org.id,
        group_id=org_a.group.id,
        template_version_id=org_a.template_version.id,
        created_by_teacher_id=org_a.teacher.id,
        title="Organization A upcoming internship",
        start_date=today,
        end_date=today + timedelta(days=10),
        deadline=today + timedelta(days=12),
        status=InternshipStatus.PUBLISHED,
    )
    other_tenant_internship = Internship(
        organization_id=org_b.org.id,
        group_id=org_b.group.id,
        template_version_id=org_b.template_version.id,
        created_by_teacher_id=org_b.teacher.id,
        title="Organization B private internship",
        start_date=today - timedelta(days=20),
        end_date=today - timedelta(days=10),
        deadline=today - timedelta(days=2),
        status=InternshipStatus.PUBLISHED,
    )
    db.add_all([overdue_internship, upcoming_internship, other_tenant_internship])
    db.flush()
    db.add_all(
        [
            Report(
                organization_id=org_a.org.id,
                internship_id=overdue_internship.id,
                student_id=org_a.student.id,
                status=ReportStatus.DRAFT,
                document_data={"private": "organization A report content"},
            ),
            Report(
                organization_id=org_a.org.id,
                internship_id=upcoming_internship.id,
                student_id=org_a.student.id,
                status=ReportStatus.SUBMITTED,
                document_data={"private": "another organization A report"},
            ),
            Report(
                organization_id=org_b.org.id,
                internship_id=other_tenant_internship.id,
                student_id=org_b.student.id,
                status=ReportStatus.DRAFT,
                document_data={"private": "organization B report content"},
            ),
        ]
    )
    db.commit()

    token = _director_token(client, db, org_a)
    response = client.get("/api/v1/director/dashboard", headers=auth_headers(token))

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["organization"]["id"] == str(org_a.org.id)
    assert payload["groups_count"] == 1
    assert payload["internships_count"] == 2
    assert payload["active_internships_count"] == 2
    assert payload["reports_count"] == 2
    assert payload["overdue_reports_count"] == 1
    assert {item["status"]: item["count"] for item in payload["report_statuses"]} == {
        "DRAFT": 1,
        "SUBMITTED": 1,
    }
    assert payload["groups"] == [
        {
            "id": str(org_a.group.id),
            "name": org_a.group.name,
            "academic_year": None,
            "student_count": 1,
            "internships_count": 2,
            "reports_count": 2,
            "overdue_reports_count": 1,
        }
    ]
    assert {item["title"] for item in payload["internships"]} == {
        "Organization A overdue internship",
        "Organization A upcoming internship",
    }
    assert payload["teacher_loads"] == [
        {
            "id": str(org_a.teacher.id),
            "full_name": "Test Teacher",
            "groups_count": 1,
            "active_internships_count": 2,
            "reports_to_review_count": 1,
        }
    ]
    assert "Organization B private internship" not in response.text
    assert "organization A report content" not in response.text
    assert "document_data" not in response.text
    assert "comments" not in response.text


@pytest.mark.parametrize("token_getter", ["teacher_token", "student_token"])
def test_director_dashboard_rejects_teacher_and_student(client, org_a: OrgFixture, token_getter: str):
    response = client.get(
        "/api/v1/director/dashboard",
        headers=auth_headers(getattr(org_a, token_getter)(client)),
    )

    assert response.status_code == 403
