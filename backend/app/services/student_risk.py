"""Early-warning "traffic light" for student reports.

Pure functions only (no database, no clock): the service passes in plain
values so every rule is unit-testable at its boundaries.

Levels:
  RED    needs the teacher's attention now (overdue, or the deadline is close
         and little is written);
  YELLOW falling behind or silent for a while;
  GREEN  on track, or already handed in.

Reasons are stable codes; the UI translates them.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any

from app.models.enums import ReportStatus


class RiskLevel(str, Enum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


# A section counts as "written" once it holds this many words.
MIN_SECTION_WORDS = 20
# RED when this close to (or past) the deadline with less than RED_COMPLETION written.
RED_DAYS_LEFT = 3
RED_COMPLETION = 0.5
# YELLOW when untouched for this many days during the practice period.
IDLE_DAYS = 5
# YELLOW when the written share trails the elapsed share of the period by more than this.
BEHIND_MARGIN = 0.25

# Reports the student no longer has to work on.
_HANDED_IN = {ReportStatus.SUBMITTED, ReportStatus.UNDER_REVIEW, ReportStatus.APPROVED, ReportStatus.LOCKED}

_LEVEL_ORDER = {RiskLevel.RED: 0, RiskLevel.YELLOW: 1, RiskLevel.GREEN: 2}


@dataclass(frozen=True)
class RiskAssessment:
    level: RiskLevel
    reasons: tuple[str, ...]


def _as_list(value: Any) -> list:
    """Stored JSON is untrusted: anything that is not a list is treated as empty."""
    return value if isinstance(value, list) else []


def _text_of_runs(runs: Any) -> str:
    parts: list[str] = []
    for run in _as_list(runs):
        if isinstance(run, dict) and run.get("kind") == "text" and isinstance(run.get("text"), str):
            parts.append(run["text"])
    return " ".join(parts)


def _block_words(block: Any, depth: int = 0) -> int:
    """Words in one document block; recursion is bounded against hostile nesting."""
    if not isinstance(block, dict) or depth > 8:
        return 0
    kind = block.get("type")
    if kind in {"paragraph", "heading"}:
        return len(_text_of_runs(block.get("runs")).split())
    total = 0
    if kind == "table":
        for row in _as_list(block.get("rows")):
            for cell in _as_list(row.get("cells") if isinstance(row, dict) else None):
                total += sum(_block_words(inner, depth + 1) for inner in _as_list(cell.get("blocks") if isinstance(cell, dict) else None))
    elif kind == "list":
        for item in _as_list(block.get("items")):
            total += sum(_block_words(inner, depth + 1) for inner in _as_list(item.get("blocks") if isinstance(item, dict) else None))
    return total


def completion_ratio(document_data: Any) -> float | None:
    """Share of student-editable sections that hold real text; None if there is nothing to write."""
    if not isinstance(document_data, dict):
        return None
    sections = [s for s in _as_list(document_data.get("sections")) if isinstance(s, dict) and s.get("editable", True)]
    if not sections:
        return None
    written = sum(
        1 for section in sections
        if sum(_block_words(block) for block in _as_list(section.get("blocks"))) >= MIN_SECTION_WORDS
    )
    return written / len(sections)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def days_idle(last_activity: datetime, start_date: date, now: datetime) -> int:
    """Whole days since the last edit, never counting time before the practice started."""
    started = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
    return max(0, (_aware(now) - max(_aware(last_activity), started)).days)


def assess(
    *,
    status: ReportStatus,
    start_date: date,
    deadline: date,
    today: date,
    completion: float | None,
    idle_days: int,
) -> RiskAssessment:
    if status in _HANDED_IN or today < start_date:
        return RiskAssessment(RiskLevel.GREEN, ())

    written = completion or 0.0
    days_left = (deadline - today).days
    if days_left < 0:
        return RiskAssessment(RiskLevel.RED, ("OVERDUE",))
    if days_left <= RED_DAYS_LEFT and written < RED_COMPLETION:
        return RiskAssessment(RiskLevel.RED, ("DEADLINE_SOON_LOW_PROGRESS",))

    reasons: list[str] = []
    if idle_days >= IDLE_DAYS:
        reasons.append("NO_RECENT_ACTIVITY")
    period = (deadline - start_date).days
    elapsed = min(1.0, max(0.0, (today - start_date).days / period)) if period > 0 else 1.0
    if written + BEHIND_MARGIN < elapsed:
        reasons.append("BEHIND_SCHEDULE")
    if reasons:
        return RiskAssessment(RiskLevel.YELLOW, tuple(reasons))
    return RiskAssessment(RiskLevel.GREEN, ())


def sort_key(level: RiskLevel, deadline: date, name: str) -> tuple[int, date, str]:
    """Most urgent first: RED, then YELLOW, then GREEN; earlier deadlines first."""
    return (_LEVEL_ORDER[level], deadline, name.casefold())
