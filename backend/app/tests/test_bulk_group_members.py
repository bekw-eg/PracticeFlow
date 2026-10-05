import uuid

from sqlalchemy import select

from app.core.security import hash_password
from app.models.group import Group
from app.models.group_member import GroupMember
from app.models.membership import OrganizationMembership
from app.models.student import Student
from app.models.teacher_group import TeacherGroup
from app.models.user import User
from app.tests.conftest import DEV_PASSWORD, OrgFixture, auth_headers


def _add_student(db, org: OrgFixture, email: str, full_name: str) -> Student:
    user = User(email=email, hashed_password=hash_password(DEV_PASSWORD), full_name=full_name)
    db.add(user)
    db.flush()
    membership = OrganizationMembership(
        user_id=user.id,
        organization_id=org.org.id,
        role_id=org.role_student.id,
    )
    db.add(membership)
    db.flush()
    student = Student(membership_id=membership.id)
    db.add(student)
    db.flush()
    return student


def _owned_group(db, org: OrgFixture, name: str) -> Group:
    group = Group(organization_id=org.org.id, name=name)
    db.add(group)
    db.flush()
    db.add(TeacherGroup(teacher_id=org.teacher.id, group_id=group.id))
    return group


def _has_membership(db, group_id, student_id) -> bool:
    return db.execute(
        select(GroupMember).where(GroupMember.group_id == group_id, GroupMember.student_id == student_id)
    ).scalar_one_or_none() is not None


def test_bulk_remove_returns_partial_result_and_keeps_other_group_memberships(client, db, org_a: OrgFixture):
    other_group = _owned_group(db, org_a, "OTHER-GROUP")
    missing_student_id = uuid.uuid4()
    db.add(GroupMember(group_id=org_a.group.id, student_id=org_a.student.id))
    db.add(GroupMember(group_id=other_group.id, student_id=org_a.student.id))
    db.commit()

    response = client.post(
        f"/api/v1/groups/{org_a.group.id}/students/bulk-remove",
        headers=auth_headers(org_a.teacher_token(client)),
        json={"student_ids": [str(org_a.student.id), str(missing_student_id)]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["succeeded_student_ids"] == [str(org_a.student.id)]
    assert body["failed"] == [{"student_id": str(missing_student_id), "code": "NOT_IN_SOURCE_GROUP"}]
    assert not _has_membership(db, org_a.group.id, org_a.student.id)
    assert _has_membership(db, other_group.id, org_a.student.id)


def test_bulk_transfer_returns_each_success_and_failure_without_removing_other_memberships(client, db, org_a: OrgFixture):
    target_group = _owned_group(db, org_a, "TARGET-GROUP")
    other_group = _owned_group(db, org_a, "OTHER-GROUP")
    movable = _add_student(db, org_a, "movable@org-a.edu", "Movable Student")
    db.add_all(
        [
            GroupMember(group_id=org_a.group.id, student_id=org_a.student.id),
            GroupMember(group_id=org_a.group.id, student_id=movable.id),
            GroupMember(group_id=target_group.id, student_id=org_a.student.id),
            GroupMember(group_id=other_group.id, student_id=movable.id),
        ]
    )
    db.commit()

    response = client.post(
        f"/api/v1/groups/{org_a.group.id}/students/bulk-transfer",
        headers=auth_headers(org_a.teacher_token(client)),
        json={"student_ids": [str(movable.id), str(org_a.student.id)], "target_group_id": str(target_group.id)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["succeeded_student_ids"] == [str(movable.id)]
    assert body["failed"] == [{"student_id": str(org_a.student.id), "code": "ALREADY_IN_TARGET_GROUP"}]
    assert not _has_membership(db, org_a.group.id, movable.id)
    assert _has_membership(db, target_group.id, movable.id)
    assert _has_membership(db, other_group.id, movable.id)
    assert _has_membership(db, org_a.group.id, org_a.student.id)


def test_bulk_transfer_rejects_target_group_outside_teacher_tenant_and_ownership(client, db, org_a: OrgFixture, org_b: OrgFixture):
    db.add(GroupMember(group_id=org_a.group.id, student_id=org_a.student.id))
    db.commit()

    response = client.post(
        f"/api/v1/groups/{org_a.group.id}/students/bulk-transfer",
        headers=auth_headers(org_a.teacher_token(client)),
        json={"student_ids": [str(org_a.student.id)], "target_group_id": str(org_b.group.id)},
    )

    assert response.status_code == 403
    assert _has_membership(db, org_a.group.id, org_a.student.id)


def test_bulk_remove_never_mutates_a_cross_tenant_student_membership(client, db, org_a: OrgFixture, org_b: OrgFixture):
    """Defend against an invalid legacy row linking a foreign student to this group."""
    db.add(GroupMember(group_id=org_a.group.id, student_id=org_b.student.id))
    db.commit()

    response = client.post(
        f"/api/v1/groups/{org_a.group.id}/students/bulk-remove",
        headers=auth_headers(org_a.teacher_token(client)),
        json={"student_ids": [str(org_b.student.id)]},
    )

    assert response.status_code == 200
    assert response.json() == {
        "succeeded_student_ids": [],
        "failed": [{"student_id": str(org_b.student.id), "code": "NOT_IN_SOURCE_GROUP"}],
    }
    assert _has_membership(db, org_a.group.id, org_b.student.id)
