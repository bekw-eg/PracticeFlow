from app.tests.conftest import OrgFixture, auth_headers
from app.tests.test_group_workflow import _internship_payload
from app.models.group_member import GroupMember


def _template_payload(response, document: dict) -> dict:
    return {"expected_revision": response.json()["revision"], "document": document}


def test_new_version_document_is_the_default_skeleton(client, org_a: OrgFixture):
    token = org_a.teacher_token(client)
    create_resp = client.post(f"/api/v1/templates/{org_a.template.id}/versions", headers=auth_headers(token), json={})
    assert create_resp.status_code == 201
    version_id = create_resp.json()["id"]

    resp = client.get(f"/api/v1/templates/{org_a.template.id}/versions/{version_id}/document", headers=auth_headers(token))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["document"]["sections"]) == 6
    assert body["is_locked"] is False
    assert body["revision"] == 1
    title_page_runs = [r for b in body["document"]["title_page"]["blocks"] for r in b.get("runs", [])]
    variable_runs = [r for r in title_page_runs if r["kind"] == "variable"]
    assert all(r["resolved_text"] is None for r in variable_runs)


def test_teacher_can_edit_unlocked_version_document(client, org_a: OrgFixture):
    token = org_a.teacher_token(client)
    get_resp = client.get(
        f"/api/v1/templates/{org_a.template.id}/versions/{org_a.template_version.id}/document",
        headers=auth_headers(token),
    )
    document = get_resp.json()["document"]
    document["sections"][0]["title"] = "Изменённое введение"
    document["meta"]["default_font_size"] = 12

    patch_resp = client.patch(
        f"/api/v1/templates/{org_a.template.id}/versions/{org_a.template_version.id}/document",
        headers=auth_headers(token),
        json=_template_payload(get_resp, document),
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["document"]["sections"][0]["title"] == "Изменённое введение"
    assert patch_resp.json()["document"]["meta"]["default_font_size"] == 12
    assert patch_resp.json()["revision"] == 2

    reget = client.get(
        f"/api/v1/templates/{org_a.template.id}/versions/{org_a.template_version.id}/document",
        headers=auth_headers(token),
    )
    assert reget.json()["document"]["sections"][0]["title"] == "Изменённое введение"


def test_renamed_template_section_is_used_in_reports_created_after_save(client, db, org_a: OrgFixture):
    teacher_token = org_a.teacher_token(client)
    document_response = client.get(
        f"/api/v1/templates/{org_a.template.id}/versions/{org_a.template_version.id}/document",
        headers=auth_headers(teacher_token),
    )
    document = document_response.json()["document"]
    document["sections"][1]["title"] = "Практическая часть"
    patch_response = client.patch(
        f"/api/v1/templates/{org_a.template.id}/versions/{org_a.template_version.id}/document",
        headers=auth_headers(teacher_token),
        json=_template_payload(document_response, document),
    )
    assert patch_response.status_code == 200

    db.add(GroupMember(group_id=org_a.group.id, student_id=org_a.student.id))
    db.commit()
    create_response = client.post(
        f"/api/v1/groups/{org_a.group.id}/internships",
        headers=auth_headers(teacher_token),
        json=_internship_payload(org_a.template_version.id),
    )
    assert create_response.status_code == 201
    internship_id = create_response.json()["id"]
    assert client.post(f"/api/v1/internships/{internship_id}/publish", headers=auth_headers(teacher_token)).status_code == 200

    student_token = org_a.student_token(client)
    report_id = client.get("/api/v1/reports", headers=auth_headers(student_token)).json()[0]["id"]
    report_document = client.get(f"/api/v1/reports/{report_id}/document", headers=auth_headers(student_token)).json()["document"]
    assert report_document["sections"][1]["title"] == "Практическая часть"


def test_update_rejects_document_with_unknown_variable(client, org_a: OrgFixture):
    token = org_a.teacher_token(client)
    get_resp = client.get(
        f"/api/v1/templates/{org_a.template.id}/versions/{org_a.template_version.id}/document",
        headers=auth_headers(token),
    )
    document = get_resp.json()["document"]
    document["sections"][0]["blocks"].append(
        {"type": "paragraph", "runs": [{"kind": "variable", "key": "not.a.real.variable"}]}
    )
    patch_resp = client.patch(
        f"/api/v1/templates/{org_a.template.id}/versions/{org_a.template_version.id}/document",
        headers=auth_headers(token),
        json=_template_payload(get_resp, document),
    )
    assert patch_resp.status_code == 422


def test_version_locks_once_used_by_an_internship(client, db, org_a: OrgFixture):
    token = org_a.teacher_token(client)

    create_resp = client.post(
        f"/api/v1/groups/{org_a.group.id}/internships",
        headers=auth_headers(token),
        json=_internship_payload(org_a.template_version.id),
    )
    assert create_resp.status_code == 201

    get_resp = client.get(
        f"/api/v1/templates/{org_a.template.id}/versions/{org_a.template_version.id}/document",
        headers=auth_headers(token),
    )
    assert get_resp.json()["is_locked"] is True

    document = get_resp.json()["document"]
    document["meta"]["default_font_size"] = 99
    patch_resp = client.patch(
        f"/api/v1/templates/{org_a.template.id}/versions/{org_a.template_version.id}/document",
        headers=auth_headers(token),
        json=_template_payload(get_resp, document),
    )
    assert patch_resp.status_code == 409


def test_student_cannot_access_template_document_endpoints(client, org_a: OrgFixture):
    token = org_a.student_token(client)
    resp = client.get(
        f"/api/v1/templates/{org_a.template.id}/versions/{org_a.template_version.id}/document",
        headers=auth_headers(token),
    )
    assert resp.status_code == 403


def test_cross_tenant_teacher_cannot_read_or_edit_template_document(client, org_a: OrgFixture, org_b: OrgFixture):
    token = org_b.teacher_token(client)
    get_resp = client.get(
        f"/api/v1/templates/{org_a.template.id}/versions/{org_a.template_version.id}/document",
        headers=auth_headers(token),
    )
    assert get_resp.status_code == 404

    own_document_response = client.get(
        f"/api/v1/templates/{org_b.template.id}/versions/{org_b.template_version.id}/document",
        headers=auth_headers(token),
    )
    patch_resp = client.patch(
        f"/api/v1/templates/{org_a.template.id}/versions/{org_a.template_version.id}/document",
        headers=auth_headers(token),
        json=_template_payload(own_document_response, own_document_response.json()["document"]),
    )
    assert patch_resp.status_code == 404


def test_get_document_response_includes_authoritative_numbering(client, org_a: OrgFixture):
    """Phase 2.5: numbering is computed server-side and returned with every
    document response — the frontend has no numbering algorithm of its own
    to drift from this one (see app/documents/numbering.py)."""
    token = org_a.teacher_token(client)
    resp = client.get(
        f"/api/v1/templates/{org_a.template.id}/versions/{org_a.template_version.id}/document",
        headers=auth_headers(token),
    )
    body = resp.json()
    assert "numbering" in body
    first_section_id = body["document"]["sections"][0]["id"]
    assert body["numbering"][first_section_id] == "1"


def test_patch_response_returns_refreshed_numbering(client, org_a: OrgFixture):
    """Adding a new numbered section mid-document must shift every
    subsequent section's number in the SAME response that saved the edit —
    proving the client never needs (or has) its own numbering logic."""
    token = org_a.teacher_token(client)
    get_resp = client.get(
        f"/api/v1/templates/{org_a.template.id}/versions/{org_a.template_version.id}/document",
        headers=auth_headers(token),
    )
    document = get_resp.json()["document"]
    original_second_section_id = document["sections"][1]["id"]
    assert get_resp.json()["numbering"][original_second_section_id] == "2"

    new_section = {
        "id": "sec_inserted",
        "key": "inserted",
        "title": "Вставленный раздел",
        "level": 1,
        "required": False,
        "editable": True,
        "page_break_before": True,
        "numbering": {"participates": True},
        "blocks": [],
    }
    document["sections"].insert(1, new_section)

    patch_resp = client.patch(
        f"/api/v1/templates/{org_a.template.id}/versions/{org_a.template_version.id}/document",
        headers=auth_headers(token),
        json=_template_payload(get_resp, document),
    )
    assert patch_resp.status_code == 200
    numbering = patch_resp.json()["numbering"]
    assert numbering["sec_inserted"] == "2"
    assert numbering[original_second_section_id] == "3"


def test_template_document_rejects_stale_revision_without_overwriting_current_content(client, org_a: OrgFixture):
    token = org_a.teacher_token(client)
    url = f"/api/v1/templates/{org_a.template.id}/versions/{org_a.template_version.id}/document"
    first_tab = client.get(url, headers=auth_headers(token)).json()
    second_tab = client.get(url, headers=auth_headers(token)).json()

    first_document = first_tab["document"]
    first_document["sections"][0]["title"] = "Сохранено первой вкладкой"
    saved = client.patch(url, headers=auth_headers(token), json={"expected_revision": first_tab["revision"], "document": first_document})
    assert saved.status_code == 200
    assert saved.json()["revision"] == first_tab["revision"] + 1

    stale_document = second_tab["document"]
    stale_document["sections"][0]["title"] = "Не должно перезаписать"
    stale = client.patch(url, headers=auth_headers(token), json={"expected_revision": second_tab["revision"], "document": stale_document})
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "STALE_DOCUMENT_REVISION"

    current = client.get(url, headers=auth_headers(token)).json()
    assert current["revision"] == saved.json()["revision"]
    assert current["document"]["sections"][0]["title"] == "Сохранено первой вкладкой"
