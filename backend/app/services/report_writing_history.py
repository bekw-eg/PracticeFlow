"""Counts-only writing history of a student's report draft.

Every successful draft save records how many words the student-editable
sections hold. Saves within ``SESSION_WINDOW`` of the previous one are folded
into the same row, so autosave produces a handful of rows per working session.
No text is stored — only counts — so the history cannot leak report content.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.report import Report
from app.models.report_writing_snapshot import ReportWritingSnapshot
from app.services.student_risk import document_word_count

SESSION_WINDOW = timedelta(minutes=10)
HISTORY_DAYS = 180
# A single save adding at least this many words is surfaced as a "large insertion".
LARGE_SAVE_WORDS = 300


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def record_save(db: Session, report: Report, previous_document: Any, new_document: Any, revision: int,
                *, now: datetime | None = None) -> ReportWritingSnapshot:
    """Add this save to the report's writing history (caller commits)."""
    instant = _aware(now or datetime.now(timezone.utc))
    words = document_word_count(new_document)
    delta = words - document_word_count(previous_document)
    latest = db.scalars(
        select(ReportWritingSnapshot)
        .where(ReportWritingSnapshot.report_id == report.id, ReportWritingSnapshot.organization_id == report.organization_id)
        .order_by(ReportWritingSnapshot.created_at.desc(), ReportWritingSnapshot.id.desc())
        .limit(1)
        .with_for_update()
    ).first()
    if latest is not None and instant - _aware(latest.updated_at) <= SESSION_WINDOW and instant >= _aware(latest.created_at):
        latest.word_count = words
        latest.revision = revision
        latest.words_added += delta
        latest.largest_save_words = max(latest.largest_save_words, delta, 0)
        latest.save_count += 1
        latest.updated_at = instant
        db.flush()
        return latest
    snapshot = ReportWritingSnapshot(
        organization_id=report.organization_id,
        report_id=report.id,
        revision=revision,
        word_count=words,
        words_added=delta,
        largest_save_words=max(delta, 0),
        save_count=1,
        created_at=instant,
        updated_at=instant,
    )
    db.add(snapshot)
    db.flush()
    return snapshot


@dataclass(frozen=True)
class WritingDay:
    day: date
    word_count: int
    words_added: int
    saves: int
    largest_save_words: int


def summarize(snapshots: list[ReportWritingSnapshot]) -> list[WritingDay]:
    """One entry per UTC day with work, oldest first; word_count is the day's last value."""
    days: dict[date, WritingDay] = {}
    for snapshot in sorted(snapshots, key=lambda item: (_aware(item.updated_at), item.id)):
        day = _aware(snapshot.created_at).astimezone(timezone.utc).date()
        previous = days.get(day)
        days[day] = WritingDay(
            day=day,
            word_count=snapshot.word_count,
            words_added=(previous.words_added if previous else 0) + snapshot.words_added,
            saves=(previous.saves if previous else 0) + snapshot.save_count,
            largest_save_words=max(previous.largest_save_words if previous else 0, snapshot.largest_save_words),
        )
    return [days[day] for day in sorted(days)]


def history_for_report(db: Session, org_id: uuid.UUID, report_id: uuid.UUID, *, now: datetime | None = None) -> dict:
    since = _aware(now or datetime.now(timezone.utc)) - timedelta(days=HISTORY_DAYS)
    snapshots = list(db.scalars(
        select(ReportWritingSnapshot)
        .where(
            ReportWritingSnapshot.organization_id == org_id,
            ReportWritingSnapshot.report_id == report_id,
            ReportWritingSnapshot.created_at >= since,
        )
        .order_by(ReportWritingSnapshot.created_at, ReportWritingSnapshot.id)
    ))
    days = summarize(snapshots)
    largest = max((day.largest_save_words for day in days), default=0)
    return {
        "current_words": days[-1].word_count if days else None,
        "active_days": len(days),
        "total_saves": sum(day.saves for day in days),
        "largest_save_words": largest,
        "large_save_threshold": LARGE_SAVE_WORDS,
        "days": [
            {"date": day.day, "word_count": day.word_count, "words_added": day.words_added, "saves": day.saves,
             "largest_save_words": day.largest_save_words}
            for day in days
        ],
    }
