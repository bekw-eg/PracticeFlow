from app.tests.conftest import OrgFixture, auth_headers


def test_student_cannot_access_teacher_only_groups_endpoint(client, org_a: OrgFixture):
    token = org_a.student_token(client)
    resp = client.get("/api/v1/groups", headers=auth_headers(token))
    assert resp.status_code == 403


def test_student_cannot_modify_group_roster(client, org_a: OrgFixture):
    token = org_a.student_token(client)
    resp = client.post(
        f"/api/v1/groups/{org_a.group.id}/students",
        headers=auth_headers(token),
        json={"student_id": str(org_a.student.id)},
    )
    assert resp.status_code == 403


def test_student_cannot_create_check_profile(client, org_a: OrgFixture):
    token = org_a.student_token(client)
    resp = client.post("/api/v1/check-profiles", headers=auth_headers(token), json={"name": "Sneaky profile"})
    assert resp.status_code == 403


def test_super_admin_placeholder_rejects_teacher(client, org_a: OrgFixture):
    token = org_a.teacher_token(client)
    resp = client.get("/api/v1/admin/dashboard", headers=auth_headers(token))
    assert resp.status_code == 403
