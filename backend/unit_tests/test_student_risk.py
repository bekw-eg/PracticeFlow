from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.enums import ReportStatus
from app.services.student_risk import (
    MIN_SECTION_WORDS,
    RiskLevel,
    assess,
    completion_ratio,
    days_idle,
    sort_key,
)

START = date(2026, 6, 1)
DEADLINE = date(2026, 6, 21)  # a 20-day period


def paragraph(words: int) -> dict:
    return {"type": "paragraph", "runs": [{"kind": "text", "text": " ".join(["слово"] * words)}]}


def section(words: int, editable: bool = True) -> dict:
    return {"id": "s", "editable": editable, "blocks": [paragraph(words)]}


def run(status=ReportStatus.DRAFT, *, today, completion, idle=0):
    return assess(status=status, start_date=START, deadline=DEADLINE, today=today,
                  completion=completion, idle_days=idle)


def test_completion_counts_only_student_editable_sections_with_enough_text():
    document = {"sections": [section(MIN_SECTION_WORDS), section(MIN_SECTION_WORDS - 1), section(500, editable=False), section(0)]}
    assert completion_ratio(document) == pytest.approx(1 / 3)


def test_completion_reads_tables_and_lists_and_survives_garbage():
    table = {"type": "table", "rows": [{"cells": [{"blocks": [paragraph(MIN_SECTION_WORDS)]}]}]}
    items = {"type": "list", "items": [{"blocks": [paragraph(MIN_SECTION_WORDS)]}]}
    document = {"sections": [{"editable": True, "blocks": [table]}, {"editable": True, "blocks": [items]}]}
    assert completion_ratio(document) == 1.0
    assert completion_ratio(None) is None
    assert completion_ratio({"sections": []}) is None
    assert completion_ratio({"sections": [{"blocks": "nope"}, 5, {"blocks": [{"type": "table", "rows": [None, {"cells": 3}]}]}]}) == 0.0


def test_deeply_nested_content_is_bounded():
    block = paragraph(100)
    for _ in range(50):
        block = {"type": "list", "items": [{"blocks": [block]}]}
    assert completion_ratio({"sections": [{"editable": True, "blocks": [block]}]}) == 0.0


@pytest.mark.parametrize("status", [ReportStatus.SUBMITTED, ReportStatus.UNDER_REVIEW, ReportStatus.APPROVED, ReportStatus.LOCKED])
def test_handed_in_reports_are_green_even_when_late_or_empty(status):
    result = run(status, today=DEADLINE + timedelta(days=30), completion=0.0, idle=99)
    assert (result.level, result.reasons) == (RiskLevel.GREEN, ())


def test_before_the_practice_starts_everything_is_green():
    assert run(today=START - timedelta(days=1), completion=0.0, idle=30).level == RiskLevel.GREEN


@pytest.mark.parametrize("status", [ReportStatus.DRAFT, ReportStatus.REVISION_REQUIRED])
def test_overdue_unsubmitted_report_is_red(status):
    result = run(status, today=DEADLINE + timedelta(days=1), completion=0.9)
    assert (result.level, result.reasons) == (RiskLevel.RED, ("OVERDUE",))


def test_deadline_day_itself_is_not_overdue():
    assert run(today=DEADLINE, completion=1.0).level == RiskLevel.GREEN


@pytest.mark.parametrize(("days_left", "completion", "level"), [
    (3, 0.49, RiskLevel.RED),
    (3, 0.5, RiskLevel.YELLOW),  # not red, yet behind a 85%-elapsed schedule
    (3, 0.75, RiskLevel.GREEN),
    (4, 0.0, RiskLevel.YELLOW),  # not red yet, but far behind schedule
    (0, 0.0, RiskLevel.RED),
])
def test_red_window_before_the_deadline(days_left, completion, level):
    result = run(today=DEADLINE - timedelta(days=days_left), completion=completion)
    assert result.level == level
    if level == RiskLevel.RED:
        assert result.reasons == ("DEADLINE_SOON_LOW_PROGRESS",)


def test_missing_completion_counts_as_nothing_written():
    assert run(today=DEADLINE - timedelta(days=1), completion=None).level == RiskLevel.RED


@pytest.mark.parametrize(("idle", "level"), [(4, RiskLevel.GREEN), (5, RiskLevel.YELLOW)])
def test_idle_threshold(idle, level):
    result = run(today=START + timedelta(days=4), completion=0.5, idle=idle)
    assert result.level == level
    assert result.reasons == (("NO_RECENT_ACTIVITY",) if level == RiskLevel.YELLOW else ())


def test_behind_schedule_margin():
    halfway = START + timedelta(days=10)  # 50% of the period has passed
    assert run(today=halfway, completion=0.25).level == RiskLevel.GREEN  # exactly at the margin
    behind = run(today=halfway, completion=0.24)
    assert (behind.level, behind.reasons) == (RiskLevel.YELLOW, ("BEHIND_SCHEDULE",))


def test_both_yellow_reasons_are_reported():
    result = run(today=START + timedelta(days=10), completion=0.0, idle=7)
    assert result.reasons == ("NO_RECENT_ACTIVITY", "BEHIND_SCHEDULE")


def test_one_day_period_does_not_divide_by_zero():
    result = assess(status=ReportStatus.DRAFT, start_date=START, deadline=START, today=START, completion=1.0, idle_days=0)
    assert result.level == RiskLevel.GREEN


def test_days_idle_ignores_time_before_start_and_naive_datetimes():
    now = datetime(2026, 6, 10, 12, tzinfo=timezone.utc)
    assert days_idle(datetime(2026, 5, 1, tzinfo=timezone.utc), START, now) == 9
    assert days_idle(datetime(2026, 6, 8, 11), START, now) == 2  # naive timestamps are treated as UTC
    assert days_idle(now + timedelta(days=1), START, now) == 0


def test_sorting_puts_most_urgent_first():
    rows = [
        (RiskLevel.GREEN, date(2026, 6, 1), "а"),
        (RiskLevel.RED, date(2026, 6, 20), "Борис"),
        (RiskLevel.YELLOW, date(2026, 6, 5), "в"),
        (RiskLevel.RED, date(2026, 6, 10), "Яна"),
        (RiskLevel.RED, date(2026, 6, 10), "Анна"),
    ]
    ordered = sorted(rows, key=lambda row: sort_key(*row))
    assert [row[2] for row in ordered] == ["Анна", "Яна", "Борис", "в", "а"]
