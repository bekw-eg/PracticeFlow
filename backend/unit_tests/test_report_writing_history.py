import uuid
from datetime import datetime, timedelta, timezone

from app.models.report_writing_snapshot import ReportWritingSnapshot
from app.services.report_writing_history import summarize
from app.services.student_risk import document_word_count


def snap(created: datetime, updated: datetime, words: int, added: int, saves: int, largest: int) -> ReportWritingSnapshot:
    return ReportWritingSnapshot(id=uuid.uuid4(), organization_id=uuid.uuid4(), report_id=uuid.uuid4(), revision=1,
                                 word_count=words, words_added=added, largest_save_words=largest, save_count=saves,
                                 created_at=created, updated_at=updated)


def test_document_word_count_ignores_locked_sections():
    text = {"type": "paragraph", "runs": [{"kind": "text", "text": "один два три"}, {"kind": "variable", "key": "x"}]}
    document = {"sections": [{"editable": True, "blocks": [text]}, {"editable": False, "blocks": [text, text]}]}
    assert document_word_count(document) == 3
    assert document_word_count(None) == 0


def test_summarize_groups_by_utc_day_and_keeps_the_days_last_word_count():
    day1 = datetime(2026, 6, 1, 9, tzinfo=timezone.utc)
    rows = [
        snap(day1 + timedelta(hours=5), day1 + timedelta(hours=5, minutes=8), 260, 60, 4, 30),
        snap(day1, day1 + timedelta(minutes=9), 200, 200, 3, 150),
        snap(day1 + timedelta(days=2), day1 + timedelta(days=2), 180, -80, 1, 0),
    ]
    days = summarize(rows)
    assert [(d.day.isoformat(), d.word_count, d.words_added, d.saves, d.largest_save_words) for d in days] == [
        ("2026-06-01", 260, 260, 7, 150),
        ("2026-06-03", 180, -80, 1, 0),
    ]


def test_summarize_uses_utc_for_late_evening_local_saves():
    almaty_evening = datetime(2026, 6, 1, 23, 30, tzinfo=timezone(timedelta(hours=5)))  # 18:30 UTC
    assert summarize([snap(almaty_evening, almaty_evening, 10, 10, 1, 10)])[0].day.isoformat() == "2026-06-01"
    assert summarize([]) == []
