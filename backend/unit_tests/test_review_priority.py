import uuid
from datetime import UTC, datetime, timedelta

from app.models.enums import DocumentCheckJobStatus
from app.services.review_priority import (
    PriorityLevel,
    RED_ERROR_COUNT_FALLBACK,
    RED_ERRORS_PER_100_PARAGRAPHS,
    RED_ISSUES_COUNT_FALLBACK,
    RED_ISSUES_PER_100_PARAGRAPHS,
    RED_SIMILARITY_PERCENT,
    YELLOW_SIMILARITY_PERCENT,
    assess_priority,
    priority_sort_key,
)


def test_failed_and_waiting_levels():
    failed = assess_priority(
        job_status=DocumentCheckJobStatus.FAILED,
        error_count=0,
        warning_count=0,
        findings_truncated=False,
        paragraph_count=None,
        similarity_percent=None,
    )
    assert failed.level == PriorityLevel.FAILED
    assert failed.reasons == ("CHECK_FAILED",)
    assert failed.density_unknown is True

    for status in (None, DocumentCheckJobStatus.QUEUED, DocumentCheckJobStatus.PROCESSING):
        waiting = assess_priority(
            job_status=status,
            error_count=0,
            warning_count=0,
            findings_truncated=False,
            paragraph_count=None,
            similarity_percent=None,
        )
        assert waiting.level == PriorityLevel.WAITING
        assert waiting.reasons == ("CHECK_IN_PROGRESS",)
        assert waiting.density_unknown is True


def test_similarity_thresholds_boundaries():
    below_yellow = assess_priority(
        job_status=DocumentCheckJobStatus.COMPLETED,
        error_count=0,
        warning_count=0,
        findings_truncated=False,
        paragraph_count=100,
        similarity_percent=YELLOW_SIMILARITY_PERCENT - 0.01,
    )
    assert below_yellow.level == PriorityLevel.GREEN

    at_yellow = assess_priority(
        job_status=DocumentCheckJobStatus.COMPLETED,
        error_count=0,
        warning_count=0,
        findings_truncated=False,
        paragraph_count=100,
        similarity_percent=YELLOW_SIMILARITY_PERCENT,
    )
    assert at_yellow.level == PriorityLevel.YELLOW
    assert "MODERATE_SIMILARITY" in at_yellow.reasons

    below_red = assess_priority(
        job_status=DocumentCheckJobStatus.COMPLETED,
        error_count=0,
        warning_count=0,
        findings_truncated=False,
        paragraph_count=100,
        similarity_percent=RED_SIMILARITY_PERCENT - 0.01,
    )
    assert below_red.level == PriorityLevel.YELLOW

    at_red = assess_priority(
        job_status=DocumentCheckJobStatus.COMPLETED,
        error_count=0,
        warning_count=0,
        findings_truncated=False,
        paragraph_count=100,
        similarity_percent=RED_SIMILARITY_PERCENT,
    )
    assert at_red.level == PriorityLevel.RED
    assert "HIGH_SIMILARITY" in at_red.reasons


def test_density_thresholds_boundaries_and_info_ignored():
    # 100 paragraphs: 14 errors -> YELLOW, 15 errors -> RED
    yellow_err = assess_priority(
        job_status=DocumentCheckJobStatus.COMPLETED,
        error_count=14,
        warning_count=0,
        findings_truncated=False,
        paragraph_count=100,
        similarity_percent=None,
    )
    assert yellow_err.level == PriorityLevel.YELLOW
    assert yellow_err.density_unknown is False
    assert yellow_err.errors_per_100_paragraphs == 14.0

    red_err = assess_priority(
        job_status=DocumentCheckJobStatus.COMPLETED,
        error_count=15,
        warning_count=0,
        findings_truncated=False,
        paragraph_count=100,
        similarity_percent=None,
    )
    assert red_err.level == PriorityLevel.RED
    assert red_err.errors_per_100_paragraphs == RED_ERRORS_PER_100_PARAGRAPHS
    assert "HIGH_ERROR_DENSITY" in red_err.reasons

    # 100 paragraphs: 119 warnings -> YELLOW, 120 warnings -> RED
    yellow_warn = assess_priority(
        job_status=DocumentCheckJobStatus.COMPLETED,
        error_count=0,
        warning_count=119,
        findings_truncated=False,
        paragraph_count=100,
        similarity_percent=None,
    )
    assert yellow_warn.level == PriorityLevel.YELLOW

    red_warn = assess_priority(
        job_status=DocumentCheckJobStatus.COMPLETED,
        error_count=0,
        warning_count=120,
        findings_truncated=False,
        paragraph_count=100,
        similarity_percent=None,
    )
    assert red_warn.level == PriorityLevel.RED
    assert red_warn.issues_per_100_paragraphs == RED_ISSUES_PER_100_PARAGRAPHS
    assert "HIGH_ISSUE_DENSITY" in red_warn.reasons

    # INFO findings are not passed into error_count/warning_count -> GREEN
    info_only = assess_priority(
        job_status=DocumentCheckJobStatus.COMPLETED,
        error_count=0,
        warning_count=0,
        findings_truncated=False,
        paragraph_count=100,
        similarity_percent=None,
    )
    assert info_only.level == PriorityLevel.GREEN
    assert info_only.reasons == ()


def test_fallback_thresholds_when_paragraph_count_missing_or_zero():
    for pcount in (None, 0):
        below_err = assess_priority(
            job_status=DocumentCheckJobStatus.COMPLETED,
            error_count=RED_ERROR_COUNT_FALLBACK - 1,
            warning_count=0,
            findings_truncated=False,
            paragraph_count=pcount,
            similarity_percent=None,
        )
        assert below_err.level == PriorityLevel.YELLOW
        assert below_err.density_unknown is True
        assert below_err.errors_per_100_paragraphs is None

        at_err = assess_priority(
            job_status=DocumentCheckJobStatus.COMPLETED,
            error_count=RED_ERROR_COUNT_FALLBACK,
            warning_count=0,
            findings_truncated=False,
            paragraph_count=pcount,
            similarity_percent=None,
        )
        assert at_err.level == PriorityLevel.RED
        assert at_err.density_unknown is True
        assert "HIGH_ERROR_COUNT" in at_err.reasons

        below_issues = assess_priority(
            job_status=DocumentCheckJobStatus.COMPLETED,
            error_count=0,
            warning_count=RED_ISSUES_COUNT_FALLBACK - 1,
            findings_truncated=False,
            paragraph_count=pcount,
            similarity_percent=None,
        )
        assert below_issues.level == PriorityLevel.YELLOW

        at_issues = assess_priority(
            job_status=DocumentCheckJobStatus.COMPLETED,
            error_count=0,
            warning_count=RED_ISSUES_COUNT_FALLBACK,
            findings_truncated=False,
            paragraph_count=pcount,
            similarity_percent=None,
        )
        assert at_issues.level == PriorityLevel.RED
        assert "HIGH_ISSUE_COUNT" in at_issues.reasons


def test_truncated_findings_always_red():
    truncated = assess_priority(
        job_status=DocumentCheckJobStatus.COMPLETED,
        error_count=0,
        warning_count=1,
        findings_truncated=True,
        paragraph_count=1000,
        similarity_percent=None,
    )
    assert truncated.level == PriorityLevel.RED
    assert "FINDINGS_TRUNCATED" in truncated.reasons


def test_priority_sort_key_ordering():
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    id_a = uuid.UUID("00000000-0000-0000-0000-000000000001")
    id_b = uuid.UUID("00000000-0000-0000-0000-000000000002")

    items = [
        ("reviewed_failed", priority_sort_key(is_reviewed_by_teacher=True, level=PriorityLevel.FAILED, similarity_percent=None, error_count=0, warning_count=0, submitted_at=t0, submission_id=id_a)),
        ("green", priority_sort_key(is_reviewed_by_teacher=False, level=PriorityLevel.GREEN, similarity_percent=0.0, error_count=0, warning_count=0, submitted_at=t0, submission_id=id_a)),
        ("waiting", priority_sort_key(is_reviewed_by_teacher=False, level=PriorityLevel.WAITING, similarity_percent=None, error_count=0, warning_count=0, submitted_at=t0, submission_id=id_a)),
        ("yellow_low_err", priority_sort_key(is_reviewed_by_teacher=False, level=PriorityLevel.YELLOW, similarity_percent=None, error_count=1, warning_count=5, submitted_at=t0, submission_id=id_a)),
        ("yellow_high_sim", priority_sort_key(is_reviewed_by_teacher=False, level=PriorityLevel.YELLOW, similarity_percent=15.0, error_count=0, warning_count=1, submitted_at=t0, submission_id=id_a)),
        ("red_b", priority_sort_key(is_reviewed_by_teacher=False, level=PriorityLevel.RED, similarity_percent=35.0, error_count=10, warning_count=0, submitted_at=t0 + timedelta(hours=1), submission_id=id_b)),
        ("red_a", priority_sort_key(is_reviewed_by_teacher=False, level=PriorityLevel.RED, similarity_percent=35.0, error_count=10, warning_count=0, submitted_at=t0 + timedelta(hours=1), submission_id=id_a)),
        ("failed", priority_sort_key(is_reviewed_by_teacher=False, level=PriorityLevel.FAILED, similarity_percent=None, error_count=0, warning_count=0, submitted_at=t0, submission_id=id_a)),
    ]
    ordered = [name for name, _ in sorted(items, key=lambda pair: pair[1])]
    assert ordered == [
        "failed",
        "red_a",
        "red_b",
        "yellow_high_sim",
        "yellow_low_err",
        "waiting",
        "green",
        "reviewed_failed",
    ]
