from app.tests.conftest import OrgFixture, auth_headers


def test_org_a_teacher_my_groups_never_includes_org_b_groups(client, org_a: OrgFixture, org_b: OrgFixture):
    token = org_a.teacher_token(client)
    resp = client.get("/api/v1/groups", headers=auth_headers(token))
    assert resp.status_code == 200
    names = [g["name"] for g in resp.json()]
    assert org_a.group.name in names
    assert org_b.group.name not in names


def test_org_a_teacher_cannot_read_org_b_group_by_id(client, org_a: OrgFixture, org_b: OrgFixture):
    token = org_a.teacher_token(client)
    resp = client.get(f"/api/v1/groups/{org_b.group.id}", headers=auth_headers(token))
    # Must not leak existence via a different status code than "not found".
    assert resp.status_code == 403


def test_group_member_add_is_tenant_scoped(client, org_a: OrgFixture, org_b: OrgFixture):
    """A teacher cannot add org_b's student into org_a's group by guessing the student_id."""
    token = org_a.teacher_token(client)
    resp = client.post(
        f"/api/v1/groups/{org_a.group.id}/students",
        headers=auth_headers(token),
        json={"student_id": str(org_b.student.id)},
    )
    assert resp.status_code == 404
