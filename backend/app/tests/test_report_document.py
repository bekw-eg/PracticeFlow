from app.models.group_member import GroupMember
from app.tests.conftest import OrgFixture, auth_headers
from app.tests.test_group_workflow import _internship_payload


def _report_payload(response: dict, sections: dict) -> dict:
    return {"expected_revision": response["revision"], "sections": sections}


def _publish_internship_with_student(client, db, org: OrgFixture) -> tuple[str, str]:
    """Returns (internship_id, report_id) for org's single seeded student."""
    db.add(GroupMember(group_id=org.group.id, student_id=org.student.id))
    db.commit()

    teacher_token = org.teacher_token(client)
    create_resp = client.post(
        f"/api/v1/groups/{org.group.id}/internships",
        headers=auth_headers(teacher_token),
        json=_internship_payload(org.template_version.id),
    )
    internship_id = create_resp.json()["id"]
    client.post(f"/api/v1/internships/{internship_id}/publish", headers=auth_headers(teacher_token))

    student_token = org.student_token(client)
    reports = client.get("/api/v1/reports", headers=auth_headers(student_token)).json()
    return internship_id, reports[0]["id"]


def test_report_document_initialized_with_resolved_variables_on_publish(client, db, org_a: OrgFixture):
    _internship_id, report_id = _publish_internship_with_student(client, db, org_a)
    student_token = org_a.student_token(client)

    resp = client.get(f"/api/v1/reports/{report_id}/document", headers=auth_headers(student_token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["editable"] is True
    assert body["revision"] == 1
    assert len(body["document"]["sections"]) == 6

    title_page_runs = [r for b in body["document"]["title_page"]["blocks"] for r in b.get("runs", [])]
    student_name_run = next(r for r in title_page_runs if r.get("key") == "student.full_name")
    assert student_name_run["resolved_text"] == org_a.student_user.full_name

    # Numbering was computed for the response, not stored in the document.
    first_section_id = body["document"]["sections"][0]["id"]
    assert body["numbering"][first_section_id] == "1"


def test_student_edit_persists_across_reload(client, db, org_a: OrgFixture):
    _internship_id, report_id = _publish_internship_with_student(client, db, org_a)
    student_token = org_a.student_token(client)

    document_response = client.get(f"/api/v1/reports/{report_id}/document", headers=auth_headers(student_token)).json()
    doc = document_response["document"]
    editable_section = doc["sections"][0]  # all default sections are editable=True
    section_id = editable_section["id"]

    new_blocks = [
        {
            "type": "paragraph",
            "style_name": "Normal",
            "runs": [{"kind": "text", "text": "Студент написал свой текст здесь.", "bold": False, "italic": False, "underline": False}],
        }
    ]
    patch_resp = client.patch(
        f"/api/v1/reports/{report_id}/document",
        headers=auth_headers(student_token),
        json=_report_payload(document_response, {section_id: new_blocks}),
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["revision"] == document_response["revision"] + 1

    # "Student reloads the page" (rule 46) — document must remain intact.
    reget = client.get(f"/api/v1/reports/{report_id}/document", headers=auth_headers(student_token))
    saved_blocks = reget.json()["document"]["sections"][0]["blocks"]
    assert len(saved_blocks) == 1
    assert saved_blocks[0]["runs"][0]["text"] == "Студент написал свой текст здесь."


def test_student_cannot_edit_locked_section(client, db, org_a: OrgFixture):
    # Teacher locks the first section (editable=False) before publishing.
    teacher_token = org_a.teacher_token(client)
    doc_resp = client.get(
        f"/api/v1/templates/{org_a.template.id}/versions/{org_a.template_version.id}/document",
        headers=auth_headers(teacher_token),
    )
    template_document_response = doc_resp.json()
    document = template_document_response["document"]
    document["sections"][0]["editable"] = False
    client.patch(
        f"/api/v1/templates/{org_a.template.id}/versions/{org_a.template_version.id}/document",
        headers=auth_headers(teacher_token),
        json={"expected_revision": template_document_response["revision"], "document": document},
    )

    _internship_id, report_id = _publish_internship_with_student(client, db, org_a)
    student_token = org_a.student_token(client)

    document_response = client.get(f"/api/v1/reports/{report_id}/document", headers=auth_headers(student_token)).json()
    doc = document_response["document"]
    locked_section_id = doc["sections"][0]["id"]
    assert doc["sections"][0]["editable"] is False

    patch_resp = client.patch(
        f"/api/v1/reports/{report_id}/document",
        headers=auth_headers(student_token),
        json=_report_payload(document_response, {locked_section_id: []}),
    )
    assert patch_resp.status_code == 403


def test_student_cannot_edit_after_submit(client, db, org_a: OrgFixture):
    _internship_id, report_id = _publish_internship_with_student(client, db, org_a)
    student_token = org_a.student_token(client)

    submit_resp = client.post(f"/api/v1/reports/{report_id}/submit", headers=auth_headers(student_token))
    assert submit_resp.status_code == 200

    doc = client.get(f"/api/v1/reports/{report_id}/document", headers=auth_headers(student_token)).json()
    assert doc["editable"] is False
    section_id = doc["document"]["sections"][0]["id"]

    patch_resp = client.patch(
        f"/api/v1/reports/{report_id}/document",
        headers=auth_headers(student_token),
        json=_report_payload(doc, {section_id: []}),
    )
    assert patch_resp.status_code == 409


def test_teacher_gets_readonly_view_of_student_report(client, db, org_a: OrgFixture):
    _internship_id, report_id = _publish_internship_with_student(client, db, org_a)
    teacher_token = org_a.teacher_token(client)

    resp = client.get(f"/api/v1/reports/{report_id}/document", headers=auth_headers(teacher_token))
    assert resp.status_code == 200
    assert resp.json()["editable"] is False

    # Teacher has no PATCH access to a student's working document at all.
    teacher_document = resp.json()
    section_id = teacher_document["document"]["sections"][0]["id"]
    patch_resp = client.patch(
        f"/api/v1/reports/{report_id}/document",
        headers=auth_headers(teacher_token),
        json=_report_payload(teacher_document, {section_id: []}),
    )
    assert patch_resp.status_code == 403


def test_cross_tenant_student_cannot_read_other_orgs_report_document(client, db, org_a: OrgFixture, org_b: OrgFixture):
    _internship_id, report_id = _publish_internship_with_student(client, db, org_a)
    org_b_student_token = org_b.student_token(client)

    resp = client.get(f"/api/v1/reports/{report_id}/document", headers=auth_headers(org_b_student_token))
    assert resp.status_code == 404


def test_cross_tenant_teacher_cannot_read_other_orgs_report_document(client, db, org_a: OrgFixture, org_b: OrgFixture):
    _internship_id, report_id = _publish_internship_with_student(client, db, org_a)
    org_b_teacher_token = org_b.teacher_token(client)

    resp = client.get(f"/api/v1/reports/{report_id}/document", headers=auth_headers(org_b_teacher_token))
    assert resp.status_code == 404


def test_report_document_rejects_stale_revision_without_overwriting_current_content(client, db, org_a: OrgFixture):
    _internship_id, report_id = _publish_internship_with_student(client, db, org_a)
    student_token = org_a.student_token(client)
    url = f"/api/v1/reports/{report_id}/document"
    first_tab = client.get(url, headers=auth_headers(student_token)).json()
    second_tab = client.get(url, headers=auth_headers(student_token)).json()
    section_id = first_tab["document"]["sections"][0]["id"]

    missing_revision = client.patch(url, headers=auth_headers(student_token), json={"sections": {section_id: []}})
    assert missing_revision.status_code == 422

    first_blocks = [
        {
            "type": "paragraph",
            "style_name": "Normal",
            "runs": [{"kind": "text", "text": "Сохранено первой вкладкой", "bold": False, "italic": False, "underline": False}],
        }
    ]
    saved = client.patch(url, headers=auth_headers(student_token), json=_report_payload(first_tab, {section_id: first_blocks}))
    assert saved.status_code == 200
    assert saved.json()["revision"] == first_tab["revision"] + 1

    stale_blocks = [
        {
            "type": "paragraph",
            "style_name": "Normal",
            "runs": [{"kind": "text", "text": "Не должно перезаписать", "bold": False, "italic": False, "underline": False}],
        }
    ]
    stale = client.patch(url, headers=auth_headers(student_token), json=_report_payload(second_tab, {section_id: stale_blocks}))
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "STALE_DOCUMENT_REVISION"

    current = client.get(url, headers=auth_headers(student_token)).json()
    assert current["revision"] == saved.json()["revision"]
    assert current["document"]["sections"][0]["blocks"][0]["runs"][0]["text"] == "Сохранено первой вкладкой"
