from app.tests.conftest import OrgFixture, auth_headers


def test_student_cannot_access_teacher_only_groups_endpoint(client, org_a: OrgFixture):
    token = org_a.student_token(client)
    resp = client.get("/api/v1/groups", headers=auth_headers(token))
    assert resp.status_code == 403


def test_teacher_cannot_access_student_only_reports_endpoint(client, org_a: OrgFixture):
    token = org_a.teacher_token(client)
    resp = client.get("/api/v1/reports", headers=auth_headers(token))
    assert resp.status_code == 403


def test_student_cannot_create_internship(client, org_a: OrgFixture):
    token = org_a.student_token(client)
    resp = client.post(
        f"/api/v1/groups/{org_a.group.id}/internships",
        headers=auth_headers(token),
        json={
            "title": "Should not be allowed",
            "template_version_id": str(org_a.template_version.id),
            "start_date": "2025-01-01",
            "end_date": "2025-02-01",
            "deadline": "2025-02-05",
        },
    )
    assert resp.status_code == 403


def test_student_cannot_create_template(client, org_a: OrgFixture):
    token = org_a.student_token(client)
    resp = client.post("/api/v1/templates", headers=auth_headers(token), json={"name": "Sneaky template"})
    assert resp.status_code == 403


def test_super_admin_placeholder_rejects_teacher(client, org_a: OrgFixture):
    token = org_a.teacher_token(client)
    resp = client.get("/api/v1/admin/dashboard", headers=auth_headers(token))
    assert resp.status_code == 403
