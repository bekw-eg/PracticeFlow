"""Pure priority-queue assessment for teacher review groups.

Pure functions only (no database, no clock): the service passes in plain
aggregated values so every rule is unit-testable at its boundaries.

Thresholds marked PROVISIONAL were checked only on a single sample
coursework (n=1); see docs/REVIEW_PRIORITY_QUEUE.md for the calibration
protocol before treating them as final policy.

Levels (most urgent first):
  FAILED   the latest relevant analysis failed and requires teacher action;
  RED      high error density / high issue density / truncated findings /
           high local similarity;
  YELLOW   has ERROR or WARNING findings, or moderate local similarity
           (INFO findings alone never trigger YELLOW);
  WAITING  analysis is queued or currently processing;
  GREEN    completed analysis with no ERROR/WARNING findings and low
           (or absent) local similarity.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from app.models.enums import DocumentCheckJobStatus


class PriorityLevel(str, Enum):
    FAILED = "FAILED"
    RED = "RED"
    YELLOW = "YELLOW"
    WAITING = "WAITING"
    GREEN = "GREEN"


# PROVISIONAL thresholds (validated on n=1 coursework; calibrate per docs/REVIEW_PRIORITY_QUEUE.md).
RED_SIMILARITY_PERCENT = 30.0
YELLOW_SIMILARITY_PERCENT = 10.0

# PROVISIONAL density thresholds per 100 non-empty checked paragraphs (when paragraph_count > 0).
RED_ERRORS_PER_100_PARAGRAPHS = 15.0
RED_ISSUES_PER_100_PARAGRAPHS = 120.0

# PROVISIONAL absolute fallback thresholds when paragraph_count is missing or 0 (legacy runs).
RED_ERROR_COUNT_FALLBACK = 15
RED_ISSUES_COUNT_FALLBACK = 120

_LEVEL_ORDER = {
    PriorityLevel.FAILED: 0,
    PriorityLevel.RED: 1,
    PriorityLevel.YELLOW: 2,
    PriorityLevel.WAITING: 3,
    PriorityLevel.GREEN: 4,
}


@dataclass(frozen=True)
class PriorityAssessment:
    level: PriorityLevel
    reasons: tuple[str, ...]
    density_unknown: bool
    errors_per_100_paragraphs: float | None
    issues_per_100_paragraphs: float | None


def assess_priority(
    *,
    job_status: DocumentCheckJobStatus | None,
    error_count: int,
    warning_count: int,
    findings_truncated: bool,
    paragraph_count: int | None,
    similarity_percent: float | None,
) -> PriorityAssessment:
    """Classify one submission into a priority level with stable reason codes."""
    if job_status == DocumentCheckJobStatus.FAILED:
        return PriorityAssessment(
            level=PriorityLevel.FAILED,
            reasons=("CHECK_FAILED",),
            density_unknown=True,
            errors_per_100_paragraphs=None,
            issues_per_100_paragraphs=None,
        )
    if job_status in (None, DocumentCheckJobStatus.QUEUED, DocumentCheckJobStatus.PROCESSING):
        return PriorityAssessment(
            level=PriorityLevel.WAITING,
            reasons=("CHECK_IN_PROGRESS",),
            density_unknown=True,
            errors_per_100_paragraphs=None,
            issues_per_100_paragraphs=None,
        )

    issues_count = error_count + warning_count
    density_unknown = paragraph_count is None or paragraph_count <= 0
    if not density_unknown:
        errors_per_100 = round(error_count * 100.0 / paragraph_count, 2)
        issues_per_100 = round(issues_count * 100.0 / paragraph_count, 2)
    else:
        errors_per_100 = None
        issues_per_100 = None

    red_reasons: list[str] = []
    if similarity_percent is not None and similarity_percent >= RED_SIMILARITY_PERCENT:
        red_reasons.append("HIGH_SIMILARITY")
    if findings_truncated:
        red_reasons.append("FINDINGS_TRUNCATED")
    if not density_unknown:
        assert errors_per_100 is not None and issues_per_100 is not None
        if errors_per_100 >= RED_ERRORS_PER_100_PARAGRAPHS:
            red_reasons.append("HIGH_ERROR_DENSITY")
        if issues_per_100 >= RED_ISSUES_PER_100_PARAGRAPHS:
            red_reasons.append("HIGH_ISSUE_DENSITY")
    else:
        if error_count >= RED_ERROR_COUNT_FALLBACK:
            red_reasons.append("HIGH_ERROR_COUNT")
        if issues_count >= RED_ISSUES_COUNT_FALLBACK:
            red_reasons.append("HIGH_ISSUE_COUNT")

    if red_reasons:
        return PriorityAssessment(
            level=PriorityLevel.RED,
            reasons=tuple(red_reasons),
            density_unknown=density_unknown,
            errors_per_100_paragraphs=errors_per_100,
            issues_per_100_paragraphs=issues_per_100,
        )

    yellow_reasons: list[str] = []
    if similarity_percent is not None and similarity_percent >= YELLOW_SIMILARITY_PERCENT:
        yellow_reasons.append("MODERATE_SIMILARITY")
    if error_count > 0:
        yellow_reasons.append("HAS_ERRORS")
    if warning_count > 0:
        yellow_reasons.append("HAS_WARNINGS")

    if yellow_reasons:
        return PriorityAssessment(
            level=PriorityLevel.YELLOW,
            reasons=tuple(yellow_reasons),
            density_unknown=density_unknown,
            errors_per_100_paragraphs=errors_per_100,
            issues_per_100_paragraphs=issues_per_100,
        )

    return PriorityAssessment(
        level=PriorityLevel.GREEN,
        reasons=(),
        density_unknown=density_unknown,
        errors_per_100_paragraphs=errors_per_100,
        issues_per_100_paragraphs=issues_per_100,
    )


def priority_sort_key(
    *,
    is_reviewed_by_teacher: bool,
    level: PriorityLevel,
    similarity_percent: float | None,
    error_count: int,
    warning_count: int,
    submitted_at: datetime,
    submission_id: uuid.UUID,
) -> tuple:
    """Unreviewed works first, then FAILED -> RED -> YELLOW -> WAITING -> GREEN."""
    return (
        1 if is_reviewed_by_teacher else 0,
        _LEVEL_ORDER[level],
        -(similarity_percent if similarity_percent is not None else -1.0),
        -error_count,
        -(error_count + warning_count),
        submitted_at,
        str(submission_id),
    )
