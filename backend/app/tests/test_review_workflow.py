from app.models.group_member import GroupMember
from app.tests.conftest import OrgFixture, auth_headers
from app.tests.test_group_workflow import _internship_payload


def _setup_submitted_report(client, db, org: OrgFixture) -> tuple[str, str, str]:
    """Returns (teacher_token, student_token, report_id) for a report with
    real content already written, submitted once, ready for review."""
    db.add(GroupMember(group_id=org.group.id, student_id=org.student.id))
    db.commit()

    teacher_token = org.teacher_token(client)
    create_resp = client.post(
        f"/api/v1/groups/{org.group.id}/internships", headers=auth_headers(teacher_token), json=_internship_payload(org.template_version.id)
    )
    internship_id = create_resp.json()["id"]
    client.post(f"/api/v1/internships/{internship_id}/publish", headers=auth_headers(teacher_token))

    student_token = org.student_token(client)
    reports = client.get("/api/v1/reports", headers=auth_headers(student_token)).json()
    report_id = reports[0]["id"]

    # The default skeleton's placeholder paragraph starts empty (Phase 2's
    # defaults.py) — write real content first so there's something for a
    # teacher to actually comment on.
    document_response = client.get(f"/api/v1/reports/{report_id}/document", headers=auth_headers(student_token)).json()
    doc = document_response["document"]
    first_section = doc["sections"][0]
    first_block = first_section["blocks"][0]
    filled_blocks = [
        {
            "type": "paragraph", "id": first_block["id"], "style_name": "Normal", "style_override": None,
            "runs": [{"kind": "text", "id": "r_seed", "text": "Өндірістік практика барысында студент білім алды.", "bold": False, "italic": False, "underline": False}],
        }
    ]
    client.patch(
        f"/api/v1/reports/{report_id}/document",
        headers=auth_headers(student_token),
        json={"expected_revision": document_response["revision"], "sections": {first_section["id"]: filled_blocks}},
    )

    client.post(f"/api/v1/reports/{report_id}/submit", headers=auth_headers(student_token))

    return teacher_token, student_token, report_id


class TestReviewStateMachine:
    def test_full_happy_path_submit_to_locked(self, client, db, org_a: OrgFixture):
        teacher_token, student_token, report_id = _setup_submitted_report(client, db, org_a)

        start_resp = client.post(f"/api/v1/reports/{report_id}/review/start", headers=auth_headers(teacher_token))
        assert start_resp.status_code == 200
        assert start_resp.json()["status"] == "UNDER_REVIEW"

        approve_resp = client.post(f"/api/v1/reports/{report_id}/review/approve", headers=auth_headers(teacher_token))
        assert approve_resp.status_code == 200
        assert approve_resp.json()["status"] == "LOCKED"

        doc = client.get(f"/api/v1/reports/{report_id}/document", headers=auth_headers(student_token)).json()
        assert doc["editable"] is False

    def test_revision_cycle_then_approval(self, client, db, org_a: OrgFixture):
        teacher_token, student_token, report_id = _setup_submitted_report(client, db, org_a)
        client.post(f"/api/v1/reports/{report_id}/review/start", headers=auth_headers(teacher_token))

        revision_resp = client.post(
            f"/api/v1/reports/{report_id}/review/request-revision",
            headers=auth_headers(teacher_token),
            json={"general_comment": "Исправьте список литературы."},
        )
        assert revision_resp.status_code == 200
        assert revision_resp.json()["status"] == "REVISION_REQUIRED"

        doc = client.get(f"/api/v1/reports/{report_id}/document", headers=auth_headers(student_token)).json()
        assert doc["editable"] is True

        resubmit_resp = client.post(f"/api/v1/reports/{report_id}/submit", headers=auth_headers(student_token))
        assert resubmit_resp.status_code == 200
        assert resubmit_resp.json()["status"] == "SUBMITTED"

        client.post(f"/api/v1/reports/{report_id}/review/start", headers=auth_headers(teacher_token))
        approve_resp = client.post(f"/api/v1/reports/{report_id}/review/approve", headers=auth_headers(teacher_token))
        assert approve_resp.json()["status"] == "LOCKED"

    def test_cannot_skip_states(self, client, db, org_a: OrgFixture):
        teacher_token, _student_token, report_id = _setup_submitted_report(client, db, org_a)
        resp = client.post(f"/api/v1/reports/{report_id}/review/approve", headers=auth_headers(teacher_token))
        assert resp.status_code == 409

    def test_cannot_request_revision_before_review_started(self, client, db, org_a: OrgFixture):
        teacher_token, _student_token, report_id = _setup_submitted_report(client, db, org_a)
        resp = client.post(f"/api/v1/reports/{report_id}/review/request-revision", headers=auth_headers(teacher_token), json={})
        assert resp.status_code == 409

    def test_student_cannot_call_review_endpoints(self, client, db, org_a: OrgFixture):
        _teacher_token, student_token, report_id = _setup_submitted_report(client, db, org_a)
        assert client.post(f"/api/v1/reports/{report_id}/review/start", headers=auth_headers(student_token)).status_code == 403
        assert client.post(f"/api/v1/reports/{report_id}/review/approve", headers=auth_headers(student_token)).status_code == 403

    def test_history_records_full_lifecycle(self, client, db, org_a: OrgFixture):
        teacher_token, student_token, report_id = _setup_submitted_report(client, db, org_a)
        client.post(f"/api/v1/reports/{report_id}/review/start", headers=auth_headers(teacher_token))
        client.post(f"/api/v1/reports/{report_id}/review/approve", headers=auth_headers(teacher_token))

        history = client.get(f"/api/v1/reports/{report_id}/history", headers=auth_headers(student_token)).json()
        events = [h["event"] for h in history]
        assert "REPORT_SUBMITTED" in events
        assert "REVIEW_STARTED" in events
        assert "REPORT_APPROVED" in events
        assert "REPORT_LOCKED" in events


class TestComments:
    def test_teacher_can_create_inline_comment_during_review(self, client, db, org_a: OrgFixture):
        teacher_token, student_token, report_id = _setup_submitted_report(client, db, org_a)
        client.post(f"/api/v1/reports/{report_id}/review/start", headers=auth_headers(teacher_token))

        document_response = client.get(f"/api/v1/reports/{report_id}/document", headers=auth_headers(teacher_token)).json()
        doc = document_response["document"]
        section = doc["sections"][0]
        block = section["blocks"][0]
        text = "".join(r["text"] for r in block["runs"] if r["kind"] == "text")
        assert text

        resp = client.post(
            f"/api/v1/reports/{report_id}/comments",
            headers=auth_headers(teacher_token),
            json={"node_id": block["id"], "start_offset": 0, "end_offset": len(text), "text_snapshot": text, "body": "Переформулируйте это предложение."},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["anchor_status"] == "valid"
        assert body["body"] == "Переформулируйте это предложение."

        student_view = client.get(f"/api/v1/reports/{report_id}/comments", headers=auth_headers(student_token)).json()
        assert len(student_view) == 1
        assert student_view[0]["anchor_status"] == "valid"

    def test_student_cannot_create_top_level_comment(self, client, db, org_a: OrgFixture):
        teacher_token, student_token, report_id = _setup_submitted_report(client, db, org_a)
        client.post(f"/api/v1/reports/{report_id}/review/start", headers=auth_headers(teacher_token))
        resp = client.post(
            f"/api/v1/reports/{report_id}/comments",
            headers=auth_headers(student_token),
            json={"node_id": "p_x", "start_offset": 0, "end_offset": 3, "text_snapshot": "abc", "body": "sneaky"},
        )
        assert resp.status_code == 403

    def test_student_can_reply_teacher_can_resolve(self, client, db, org_a: OrgFixture):
        teacher_token, student_token, report_id = _setup_submitted_report(client, db, org_a)
        client.post(f"/api/v1/reports/{report_id}/review/start", headers=auth_headers(teacher_token))

        general = client.post(
            f"/api/v1/reports/{report_id}/comments/general", headers=auth_headers(teacher_token), json={"body": "Общий комментарий."}
        ).json()

        reply_resp = client.post(
            f"/api/v1/reports/{report_id}/comments/{general['id']}/replies", headers=auth_headers(student_token), json={"body": "Исправил."}
        )
        assert reply_resp.status_code == 201
        assert len(reply_resp.json()["replies"]) == 1

        resolve_resp = client.post(f"/api/v1/reports/{report_id}/comments/{general['id']}/resolve", headers=auth_headers(teacher_token))
        assert resolve_resp.status_code == 200
        assert resolve_resp.json()["status"] == "RESOLVED"

    def test_student_cannot_resolve_comments(self, client, db, org_a: OrgFixture):
        teacher_token, student_token, report_id = _setup_submitted_report(client, db, org_a)
        client.post(f"/api/v1/reports/{report_id}/review/start", headers=auth_headers(teacher_token))
        general = client.post(
            f"/api/v1/reports/{report_id}/comments/general", headers=auth_headers(teacher_token), json={"body": "x"}
        ).json()
        resp = client.post(f"/api/v1/reports/{report_id}/comments/{general['id']}/resolve", headers=auth_headers(student_token))
        assert resp.status_code == 403

    def test_general_comment_created_by_request_revision(self, client, db, org_a: OrgFixture):
        teacher_token, student_token, report_id = _setup_submitted_report(client, db, org_a)
        client.post(f"/api/v1/reports/{report_id}/review/start", headers=auth_headers(teacher_token))
        client.post(
            f"/api/v1/reports/{report_id}/review/request-revision",
            headers=auth_headers(teacher_token),
            json={"general_comment": "Нужно доработать введение."},
        )
        comments = client.get(f"/api/v1/reports/{report_id}/comments", headers=auth_headers(student_token)).json()
        assert any(c["is_general"] and c["body"] == "Нужно доработать введение." for c in comments)

    def test_comment_anchor_becomes_invalid_after_student_edits_that_text(self, client, db, org_a: OrgFixture):
        teacher_token, student_token, report_id = _setup_submitted_report(client, db, org_a)
        client.post(f"/api/v1/reports/{report_id}/review/start", headers=auth_headers(teacher_token))

        document_response = client.get(f"/api/v1/reports/{report_id}/document", headers=auth_headers(teacher_token)).json()
        doc = document_response["document"]
        section = doc["sections"][0]
        block = section["blocks"][0]
        text = "".join(r["text"] for r in block["runs"] if r["kind"] == "text")

        comment = client.post(
            f"/api/v1/reports/{report_id}/comments",
            headers=auth_headers(teacher_token),
            json={"node_id": block["id"], "start_offset": 0, "end_offset": len(text), "text_snapshot": text, "body": "Fix this"},
        ).json()
        assert comment["anchor_status"] == "valid"

        client.post(f"/api/v1/reports/{report_id}/review/request-revision", headers=auth_headers(teacher_token), json={})

        new_blocks = [
            {"type": "paragraph", "id": block["id"], "style_name": "Normal", "style_override": None,
             "runs": [{"kind": "text", "id": "r_new", "text": "Совершенно другой текст.", "bold": False, "italic": False, "underline": False}]}
        ]
        patch_resp = client.patch(
            f"/api/v1/reports/{report_id}/document",
            headers=auth_headers(student_token),
            json={"expected_revision": document_response["revision"], "sections": {section["id"]: new_blocks}},
        )
        assert patch_resp.status_code == 200

        comments_after = client.get(f"/api/v1/reports/{report_id}/comments", headers=auth_headers(teacher_token)).json()
        assert comments_after[0]["anchor_status"] == "invalid"
        assert comments_after[0]["body"] == "Fix this"

    def test_comment_anchor_remains_valid_when_unrelated_text_changes(self, client, db, org_a: OrgFixture):
        teacher_token, student_token, report_id = _setup_submitted_report(client, db, org_a)
        client.post(f"/api/v1/reports/{report_id}/review/start", headers=auth_headers(teacher_token))

        document_response = client.get(f"/api/v1/reports/{report_id}/document", headers=auth_headers(teacher_token)).json()
        doc = document_response["document"]
        commented_section = doc["sections"][0]
        other_section = doc["sections"][1]
        block = commented_section["blocks"][0]
        text = "".join(r["text"] for r in block["runs"] if r["kind"] == "text")

        client.post(
            f"/api/v1/reports/{report_id}/comments",
            headers=auth_headers(teacher_token),
            json={"node_id": block["id"], "start_offset": 0, "end_offset": len(text), "text_snapshot": text, "body": "Fix this"},
        )

        client.post(f"/api/v1/reports/{report_id}/review/request-revision", headers=auth_headers(teacher_token), json={})

        other_block = other_section["blocks"][0]
        new_blocks = [
            {"type": "paragraph", "id": other_block["id"], "style_name": "Normal", "style_override": None,
             "runs": [{"kind": "text", "id": "r_new2", "text": "Unrelated edit.", "bold": False, "italic": False, "underline": False}]}
        ]
        client.patch(
            f"/api/v1/reports/{report_id}/document",
            headers=auth_headers(student_token),
            json={"expected_revision": document_response["revision"], "sections": {other_section["id"]: new_blocks}},
        )

        comments_after = client.get(f"/api/v1/reports/{report_id}/comments", headers=auth_headers(teacher_token)).json()
        assert comments_after[0]["anchor_status"] == "valid"

    def test_comments_endpoints_reject_wrong_org(self, client, db, org_a: OrgFixture, org_b: OrgFixture):
        teacher_token, _student_token, report_id = _setup_submitted_report(client, db, org_a)
        client.post(f"/api/v1/reports/{report_id}/review/start", headers=auth_headers(teacher_token))

        org_b_teacher_token = org_b.teacher_token(client)
        list_resp = client.get(f"/api/v1/reports/{report_id}/comments", headers=auth_headers(org_b_teacher_token))
        assert list_resp.status_code == 404

        create_resp = client.post(
            f"/api/v1/reports/{report_id}/comments/general", headers=auth_headers(org_b_teacher_token), json={"body": "x"}
        )
        assert create_resp.status_code == 404
