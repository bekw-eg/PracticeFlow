from app.core.security import hash_password
from app.models.enums import RoleName
from app.models.membership import OrganizationMembership
from app.models.student import Student
from app.models.user import User
from app.tests.conftest import DEV_PASSWORD, OrgFixture, _get_or_create_role, auth_headers


def _add_member(db, org: OrgFixture, *, email: str, full_name: str, role: RoleName = RoleName.STUDENT) -> tuple[User, OrganizationMembership]:
    user = User(email=email, full_name=full_name, hashed_password=hash_password(DEV_PASSWORD))
    db.add(user)
    db.flush()
    membership = OrganizationMembership(
        user_id=user.id,
        organization_id=org.org.id,
        role_id=_get_or_create_role(db, role).id,
    )
    db.add(membership)
    db.flush()
    if role == RoleName.STUDENT:
        db.add(Student(membership_id=membership.id))
    db.commit()
    return user, membership


def test_member_search_is_paginated_and_cannot_cross_tenant(client, db, org_a: OrgFixture, org_b: OrgFixture):
    director, _ = _add_member(
        db,
        org_a,
        email="director@org-a.edu",
        full_name="Director A",
        role=RoleName.DIRECTOR,
    )
    expected, _ = _add_member(db, org_a, email="needle@org-a.edu", full_name="Needle Member")
    _add_member(db, org_b, email="needle@org-b.edu", full_name="Needle Outsider")
    token = org_a.login(client, director.email)

    response = client.get("/api/v1/management/members?q=needle&offset=0&limit=1", headers=auth_headers(token))

    assert response.status_code == 200
    assert response.headers["X-Total-Count"] == "1"
    assert response.headers["X-Has-More"] == "false"
    assert [item["user_id"] for item in response.json()] == [str(expected.id)]


def test_available_student_search_keeps_tenant_scope_and_metadata(client, db, org_a: OrgFixture, org_b: OrgFixture):
    expected, expected_membership = _add_member(db, org_a, email="available@org-a.edu", full_name="Available Needle")
    _add_member(db, org_b, email="available@org-b.edu", full_name="Available Needle Outsider")
    expected_student = db.query(Student).filter_by(membership_id=expected_membership.id).one()
    token = org_a.teacher_token(client)

    response = client.get(
        f"/api/v1/groups/{org_a.group.id}/available-students?q=needle&offset=0&limit=1",
        headers=auth_headers(token),
    )

    assert response.status_code == 200
    assert response.headers["X-Total-Count"] == "1"
    assert response.headers["X-Has-More"] == "false"
    assert response.json() == [
        {
            "id": str(expected_student.id),
            "full_name": expected.full_name,
            "email": expected.email,
            "specialty_name": None,
        }
    ]
