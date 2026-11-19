from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models.report import Report
from app.models.report_writing_snapshot import ReportWritingSnapshot
from app.services.report_writing_history import SESSION_WINDOW, record_save
from app.tests.conftest import OrgFixture, auth_headers
from app.tests.test_report_document import _publish_internship_with_student


def _paragraph(words: int, word: str = "слово") -> dict:
    return {"type": "paragraph", "style_name": "Normal",
            "runs": [{"kind": "text", "text": " ".join([word] * words), "bold": False, "italic": False, "underline": False}]}


def _save(client, token: str, report_id: str, words: int) -> None:
    current = client.get(f"/api/v1/reports/{report_id}/document", headers=auth_headers(token)).json()
    section_id = current["document"]["sections"][0]["id"]
    response = client.patch(f"/api/v1/reports/{report_id}/document", headers=auth_headers(token),
                            json={"expected_revision": current["revision"], "sections": {section_id: [_paragraph(words)]}})
    assert response.status_code == 200, response.text


def _history(client, org: OrgFixture, report_id: str):
    return client.get(f"/api/v1/reports/{report_id}/writing-history", headers=auth_headers(org.teacher_token(client)))


def test_draft_saves_build_a_counts_only_history_for_the_teacher(client, db, org_a: OrgFixture):
    _internship_id, report_id = _publish_internship_with_student(client, db, org_a)
    student = org_a.student_token(client)
    _save(client, student, report_id, 40)
    _save(client, student, report_id, 400)  # a big jump in one save
    _save(client, student, report_id, 390)

    response = _history(client, org_a, report_id)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["current_words"] == 390
    assert body["total_saves"] == 3
    assert body["active_days"] == 1
    assert body["largest_save_words"] == 360
    assert body["large_save_threshold"] == 300
    assert body["days"][0]["words_added"] == 390
    assert "слово" not in response.text  # never returns the text itself
    # Autosave within the session window folds into one row.
    assert db.scalar(select(ReportWritingSnapshot.save_count)) == 3


def test_saves_after_a_pause_open_a_new_session(db, org_a: OrgFixture, client):
    _internship_id, report_id = _publish_internship_with_student(client, db, org_a)
    report = db.get(Report, report_id)
    start = datetime(2026, 6, 1, 9, tzinfo=timezone.utc)
    doc = lambda words: {"sections": [{"editable": True, "blocks": [_paragraph(words)]}]}  # noqa: E731
    record_save(db, report, doc(0), doc(50), 2, now=start)
    record_save(db, report, doc(50), doc(80), 3, now=start + SESSION_WINDOW)
    record_save(db, report, doc(80), doc(70), 4, now=start + SESSION_WINDOW * 2 + timedelta(seconds=1))
    db.commit()

    rows = db.scalars(select(ReportWritingSnapshot).order_by(ReportWritingSnapshot.created_at)).all()

    assert [(r.word_count, r.words_added, r.save_count, r.largest_save_words, r.revision) for r in rows] == [
        (80, 80, 2, 50, 3),
        (70, -10, 1, 0, 4),
    ]


def test_new_report_without_saves_has_empty_history(client, db, org_a: OrgFixture):
    _internship_id, report_id = _publish_internship_with_student(client, db, org_a)
    body = _history(client, org_a, report_id).json()
    assert body == {"current_words": None, "active_days": 0, "total_saves": 0, "largest_save_words": 0,
                    "large_save_threshold": 300, "days": []}


def test_student_cannot_read_writing_history(client, db, org_a: OrgFixture):
    _internship_id, report_id = _publish_internship_with_student(client, db, org_a)
    response = client.get(f"/api/v1/reports/{report_id}/writing-history", headers=auth_headers(org_a.student_token(client)))
    assert response.status_code == 403


def test_teacher_of_another_organization_cannot_read_writing_history(client, db, org_a: OrgFixture, org_b: OrgFixture):
    _internship_id, report_id = _publish_internship_with_student(client, db, org_a)
    _save(client, org_a.student_token(client), report_id, 25)
    response = _history(client, org_b, report_id)
    assert response.status_code in (403, 404)
    assert "current_words" not in response.text


def test_history_window_excludes_very_old_sessions(client, db, org_a: OrgFixture):
    _internship_id, report_id = _publish_internship_with_student(client, db, org_a)
    report = db.get(Report, report_id)
    old = datetime.now(timezone.utc) - timedelta(days=400)
    record_save(db, report, None, {"sections": [{"editable": True, "blocks": [_paragraph(10)]}]}, 2, now=old)
    db.commit()
    assert _history(client, org_a, report_id).json()["days"] == []
