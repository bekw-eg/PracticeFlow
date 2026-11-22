"""API, access-control, tenant-isolation and pinned-job tests for review priority queue."""
import json
import uuid
from datetime import UTC, datetime

from app.core.config import settings
from app.models.document_check import DocumentCheckJob, LocalPlagiarismRun
from app.models.enums import CheckRuleSeverity, DocumentCheckJobStatus
from app.services.document_analyzer import ANALYZER_VERSION, AnalyzerFinding, AnalyzerRule
from app.services.document_check_job_service import DocumentCheckJobService
from app.tests.conftest import auth_headers
from app.tests.test_document_check_phase21 import (
    _additional_actor,
    phase21_database_guards,  # noqa: F401
    private_storage,  # noqa: F401
)
from app.tests.test_review_groups import BASE, accepted, complete, review_guards, setup_group  # noqa: F401


def _finish_with_findings(db, expected_id, *, findings_spec, paragraph_count=100, truncated=False, similarity_percent=None):
    service = DocumentCheckJobService(db)
    job = service.claim_next("priority-test")
    assert str(job.id) == expected_id
    _, rules = service.payload(job.id, "priority-test")
    base_rule = rules[0]
    findings = []
    for severity, count in findings_spec:
        rule = AnalyzerRule(
            id=base_rule.id,
            rule_type=base_rule.rule_type,
            category=base_rule.category,
            severity=severity,
            config={},
        )
        for i in range(count):
            findings.append(
                AnalyzerFinding(
                    rule.id,
                    rule.rule_type,
                    rule.category,
                    severity,
                    "PAGE_MARGIN_MISMATCH",
                    "margin_top_mm",
                    {"section_index": i + 1},
                    {"value": 20},
                    {"value": 10},
                )
            )
    # Align rule severities in snapshot/run_rule if needed by using base_rule severity directly
    # Note: DocumentCheckJobService.complete checks finding severity matches rule severity,
    # so we update the job's run_rule severity or create findings matching base_rule when using single-rule profile.
    assert service.complete(
        job.id,
        "priority-test",
        findings,
        {
            "analyzer_version": ANALYZER_VERSION,
            "rules_total": len(rules),
            "rules_evaluated": len(rules),
            "rules_skipped": 0,
            "findings_count": len(findings),
            "findings_truncated": truncated,
            "paragraph_count": paragraph_count,
        },
    )
    if similarity_percent is not None:
        stored_job = db.get(DocumentCheckJob, job.id)
        now = datetime.now(UTC)
        run = stored_job.plagiarism_run
        if run is None:
            run = LocalPlagiarismRun(
                organization_id=stored_job.organization_id,
                job_id=stored_job.id,
                target_submission_id=stored_job.teacher_submission_id,
                queued_at=now,
                algorithm_version="local-exact-sequence-v1",
                minimum_match_words=8,
            )
            db.add(run)
        run.status = DocumentCheckJobStatus.COMPLETED
        run.started_at = run.started_at or now
        run.finished_at = now
        run.target_word_count = 100
        run.excluded_word_count = 0
        run.matched_word_count = int(similarity_percent)
        run.similarity_percent = similarity_percent
        run.candidate_documents_available = 1
        run.candidate_documents_scanned = 1
        run.matches_count = 1
        run.matches_truncated = False
        db.commit()


def test_priority_queue_access_and_org_isolation(client, db, org_a, org_b, setup_group):  # noqa: F811
    headers, _, group_id = setup_group
    path = f"{BASE}/groups/{group_id}/priority-queue"
    ok = client.get(path, headers=headers)
    assert ok.status_code == 200
    assert ok.headers["Cache-Control"] == "private, no-store"
    assert ok.json() == []

    other_teacher, _ = _additional_actor(db, org_a, teacher=True)
    for token, expected in (
        (org_a.login(client, other_teacher.email), 404),
        (org_b.teacher_token(client), 404),
        (org_a.student_token(client), 403),
    ):
        assert client.get(path, headers=auth_headers(token)).status_code == expected


def test_priority_queue_ordering_pinned_job_and_no_content(client, db, setup_group):  # noqa: F811
    headers, _, group_id = setup_group

    # 1. WAITING (QUEUED)
    waiting_sub = accepted(client, setup_group, student_label="Waiting Student", work_title="W1")

    # 2. FAILED
    failed_sub = accepted(client, setup_group, student_label="Failed Student", work_title="F1")
    job_svc = DocumentCheckJobService(db)
    # Claim waiting_sub first (FIFO), leave it PROCESSING so it's still WAITING
    claimed_waiting = job_svc.claim_next("worker-1")
    assert str(claimed_waiting.id) == waiting_sub["job"]["id"]
    for attempt in range(settings.DOCUMENT_CHECK_WORKER_MAX_ATTEMPTS):
        claimed_failed = job_svc.claim_next("worker-1")
        assert str(claimed_failed.id) == failed_sub["job"]["id"]
        expected_status = (
            DocumentCheckJobStatus.FAILED
            if attempt == settings.DOCUMENT_CHECK_WORKER_MAX_ATTEMPTS - 1
            else DocumentCheckJobStatus.QUEUED
        )
        assert job_svc.retry_or_fail(claimed_failed.id, "worker-1", "CHECK_ANALYSIS_FAILED") == expected_status

    # 3. GREEN (0 errors, 0 warnings, similarity 5%)
    green_sub = accepted(client, setup_group, student_label="Green Student", work_title="G1")
    _finish_with_findings(db, green_sub["job"]["id"], findings_spec=[], paragraph_count=100, similarity_percent=5.0)

    # 4. YELLOW (1 ERROR < 15/100 paragraphs, similarity 12%)
    yellow_sub = accepted(client, setup_group, student_label="Yellow Student", work_title="Y1")
    _finish_with_findings(
        db,
        yellow_sub["job"]["id"],
        findings_spec=[(CheckRuleSeverity.ERROR, 1)],
        paragraph_count=100,
        similarity_percent=12.0,
    )

    # 5. RED (15 ERRORs / 100 paragraphs)
    red_sub = accepted(client, setup_group, student_label="Red Student", work_title="R1")
    _finish_with_findings(
        db,
        red_sub["job"]["id"],
        findings_spec=[(CheckRuleSeverity.ERROR, 15)],
        paragraph_count=100,
        similarity_percent=2.0,
    )

    # 6. REVIEWED RED (completed by teacher -> must sort AFTER all unreviewed works, and use pinned job)
    reviewed_sub = accepted(client, setup_group, student_label="Reviewed Student", work_title="RV1")
    _finish_with_findings(
        db,
        reviewed_sub["job"]["id"],
        findings_spec=[(CheckRuleSeverity.ERROR, 16)],
        paragraph_count=100,
        similarity_percent=40.0,
    )
    assert complete(client, headers, reviewed_sub).status_code == 200

    # Trigger a recheck on reviewed_sub; priority queue must still pin completed_job_id, not the new QUEUED job
    draft = client.get(f"{BASE}/submissions/{reviewed_sub['id']}/settings", headers=headers).json()
    recheck = client.post(
        f"{BASE}/submissions/{reviewed_sub['id']}/recheck",
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
        json={"revision": draft["revision"]},
    )
    assert recheck.status_code == 200

    resp = client.get(f"{BASE}/groups/{group_id}/priority-queue", headers=headers)
    assert resp.status_code == 200
    items = resp.json()
    assert [item["student_label"] for item in items] == [
        "Failed Student",
        "Red Student",
        "Yellow Student",
        "Waiting Student",
        "Green Student",
        "Reviewed Student",
    ]
    assert [item["priority_level"] for item in items] == [
        "FAILED",
        "RED",
        "YELLOW",
        "WAITING",
        "GREEN",
        "RED",
    ]
    assert items[-1]["is_reviewed_by_teacher"] is True
    assert items[-1]["evaluated_job_id"] == reviewed_sub["job"]["id"]
    assert items[0]["density_unknown"] is True
    assert items[1]["density_unknown"] is False
    assert items[1]["errors_per_100_paragraphs"] == 15.0

    # Ensure no document content or similarity source disclosure appears in payload
    serialized = json.dumps(items)
    for forbidden in ("source_submission_id", "target_excerpt", "source_excerpt", "matches", "html"):
        assert forbidden not in serialized
