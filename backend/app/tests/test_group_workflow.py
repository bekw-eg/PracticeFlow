from app.tests.conftest import OrgFixture, auth_headers


def test_group_detail_lists_students(client, db, org_a: OrgFixture):
    from app.models.group_member import GroupMember

    db.add(GroupMember(group_id=org_a.group.id, student_id=org_a.student.id))
    db.commit()

    token = org_a.teacher_token(client)
    resp = client.get(f"/api/v1/groups/{org_a.group.id}", headers=auth_headers(token))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["students"]) == 1
    assert body["students"][0]["email"] == org_a.student_user.email


def test_legacy_report_and_template_routes_are_removed(client, org_a: OrgFixture):
    headers = auth_headers(org_a.teacher_token(client))
    for path in ("/api/v1/templates", "/api/v1/reports", "/api/v1/variables/catalog", "/api/v1/files"):
        assert client.get(path, headers=headers).status_code == 404
    assert client.get(f"/api/v1/groups/{org_a.group.id}/internships", headers=headers).status_code == 404
