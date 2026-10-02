"""Organization-local exact-text similarity checks for immutable DOCX originals.

The module deliberately reports *textual matches*, not an accusation of
plagiarism.  It compares only the current organization collection and keeps
the comparison corpus private.  Source identity and excerpts are disclosed
only when the source Teacher explicitly allowed it or owns the source.
"""
from __future__ import annotations

import re
import uuid
import zipfile
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any, BinaryIO, Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document_check import (
    DocumentCheckJob,
    LocalPlagiarismIndex,
    LocalPlagiarismMatch,
    LocalPlagiarismParagraph,
    LocalPlagiarismRun,
    TeacherDocumentSubmission,
    TeacherDocumentLifecycle,
)
from app.models.enums import AuditEventType, DocumentCheckJobStatus
from app.services.audit_service import AuditService
from app.services.document_analyzer import NS, _Styles, _xml, first_page_scope
from app.services.document_paragraphs import paragraph_structure


ALGORITHM_VERSION = "local-exact-sequence-v1"
SAFE_ERROR_CODE = "LOCAL_SIMILARITY_ANALYSIS_FAILED"
SAFE_ERROR_MESSAGE = "The local similarity check could not be completed. Please try again later."

_WORD = re.compile(r"[^\W\d_]+(?:[-'][^\W\d_]+)*", re.UNICODE)
_QUOTE_STYLE = re.compile(r"(?:quote|citation|цитат|дәйексөз)", re.IGNORECASE)
_QUOTED_PARAGRAPH = re.compile(r"^(?:[«\"“]).{20,}(?:[»\"”])(?:\s*(?:\[[^]]{1,40}\]|\([^)]{1,80}\)))?$", re.DOTALL)
_REFERENCE_HEADINGS = {
    "список литературы", "список использованных источников", "список использованной литературы",
    "библиография", "references", "bibliography", "literature", "әдебиеттер тізімі",
    "пайдаланылған әдебиеттер", "пайдаланылған әдебиеттер тізімі",
}
_TITLE_OR_CONTENT_HEADINGS = {"содержание", "оглавление", "contents", "table of contents", "мазмұны"}


def _tokens(text: str) -> list[str]:
    return [word.casefold() for word in _WORD.findall(text)]


def _paragraph_text(paragraph, allowed_text_nodes: set | None) -> str:
    values = []
    for node in paragraph.findall(".//w:t", NS):
        if allowed_text_nodes is None or node in allowed_text_nodes:
            values.append(node.text or "")
    return " ".join("".join(values).split())


def _style_is_quote(paragraph, resolver: _Styles) -> bool:
    ppr = paragraph.find("w:pPr", NS)
    style = ppr.find("w:pStyle", NS) if ppr is not None else None
    style_id = style.get(f"{{{NS['w']}}}val") if style is not None else None
    for style in resolver._chain(style_id or resolver.default_paragraph_style):
        name = style.get(f"{{{NS['w']}}}styleId") or ""
        style_name = style.find("w:name", NS)
        value = style_name.get(f"{{{NS['w']}}}val") if style_name is not None else ""
        if _QUOTE_STYLE.search(f"{name} {value}"):
            return True
    return False


def extract_local_similarity_paragraphs(
    source: str | BinaryIO,
    *,
    max_words: int,
    max_words_per_paragraph: int = 5_000,
) -> dict[str, Any]:
    """Extract normalized body paragraphs without storing titles, quotes or references.

    This runs in the same spawned worker process that parses the DOCX format.
    Results contain normalized text only; original bytes stay in private object
    storage and are never sent to the browser by this routine.
    """
    with zipfile.ZipFile(source) as package:
        document = _xml(package.read("word/document.xml"))
        styles = _xml(package.read("word/styles.xml")) if "word/styles.xml" in package.namelist() else None
        theme = _xml(package.read("word/theme/theme1.xml")) if "word/theme/theme1.xml" in package.namelist() else None
    resolver = _Styles(styles, theme)
    scope = first_page_scope(document, resolver)
    included_text_nodes = scope.texts if scope.status == "APPLIED" else None
    included_paragraphs = scope.paragraphs if scope.status == "APPLIED" else None

    records: list[dict[str, Any]] = []
    eligible_words = 0
    excluded_words = 0
    in_references = False
    for index, paragraph in enumerate(document.findall(".//w:p", NS), 1):
        full_text = _paragraph_text(paragraph, included_text_nodes)
        words = _tokens(full_text)
        if not words:
            continue
        heading = " ".join(words[:20])
        is_heading = bool(paragraph_structure(paragraph, resolver))
        in_table = bool(paragraph.xpath("ancestor::w:tc", namespaces=NS))
        excluded = (
            (included_paragraphs is not None and paragraph not in included_paragraphs)
            or in_references
            or heading in _TITLE_OR_CONTENT_HEADINGS
            or is_heading
            or in_table
            or _style_is_quote(paragraph, resolver)
            or bool(_QUOTED_PARAGRAPH.fullmatch(full_text))
        )
        if heading in _REFERENCE_HEADINGS:
            in_references = True
            excluded = True
        if excluded:
            excluded_words += len(words)
            continue
        if eligible_words >= max_words:
            excluded_words += len(words)
            continue
        accepted = words[: min(max_words_per_paragraph, max_words - eligible_words)]
        if len(accepted) < 1:
            excluded_words += len(words)
            continue
        eligible_words += len(accepted)
        if len(accepted) != len(words):
            excluded_words += len(words) - len(accepted)
        records.append({
            "paragraph_index": index,
            "normalized_text": " ".join(accepted),
            "word_count": len(accepted),
        })
    return {
        "paragraphs": records,
        "eligible_word_count": eligible_words,
        "excluded_word_count": excluded_words,
    }


def _excerpt(words: list[str], start: int, length: int) -> str:
    before = max(0, start - 5)
    after = min(len(words), start + length + 5)
    value = " ".join(words[before:after])
    if before:
        value = "… " + value
    if after < len(words):
        value += " …"
    return value[:1_000]


def _ngrams(words: list[str], size: int) -> dict[tuple[str, ...], list[int]]:
    values: dict[tuple[str, ...], list[int]] = defaultdict(list)
    for position in range(0, len(words) - size + 1):
        values[tuple(words[position:position + size])].append(position)
    return values


def _extend_match(target: list[str], source: list[str], target_start: int, source_start: int, size: int) -> tuple[int, int, int]:
    while target_start > 0 and source_start > 0 and target[target_start - 1] == source[source_start - 1]:
        target_start -= 1
        source_start -= 1
        size += 1
    while target_start + size < len(target) and source_start + size < len(source) and target[target_start + size] == source[source_start + size]:
        size += 1
    return target_start, source_start, size


def find_local_similarity_matches(
    target_paragraphs: Iterable[dict[str, Any]],
    source_paragraphs: Iterable[tuple[LocalPlagiarismParagraph, TeacherDocumentSubmission]],
    *,
    minimum_match_words: int,
    max_matches: int,
) -> tuple[list[dict[str, Any]], int, bool]:
    """Return maximal exact word sequences and unique target words they cover."""
    target = [(item["paragraph_index"], item["normalized_text"].split()) for item in target_paragraphs]
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    hard_limit = max_matches * 10
    for source_paragraph, source_submission in source_paragraphs:
        source_words = source_paragraph.normalized_text.split()
        if len(source_words) < minimum_match_words:
            continue
        source_grams = _ngrams(source_words, minimum_match_words)
        for target_index, target_words in target:
            if len(target_words) < minimum_match_words:
                continue
            target_grams = _ngrams(target_words, minimum_match_words)
            for gram in target_grams.keys() & source_grams.keys():
                for target_start in target_grams[gram]:
                    for source_start in source_grams[gram]:
                        target_start, source_start, length = _extend_match(
                            target_words, source_words, target_start, source_start, minimum_match_words
                        )
                        identity = (
                            target_index, target_start, length, source_submission.id,
                            source_paragraph.paragraph_index, source_start,
                        )
                        if identity in seen:
                            continue
                        seen.add(identity)
                        candidates.append({
                            "source_submission_id": source_submission.id,
                            "target_paragraph_index": target_index,
                            "source_paragraph_index": source_paragraph.paragraph_index,
                            "matched_word_count": length,
                            "target_start": target_start,
                            "target_excerpt": _excerpt(target_words, target_start, length),
                            "source_excerpt": _excerpt(source_words, source_start, length),
                        })
                        if len(candidates) >= hard_limit:
                            break
                    if len(candidates) >= hard_limit:
                        break
                if len(candidates) >= hard_limit:
                    break
            if len(candidates) >= hard_limit:
                break
        if len(candidates) >= hard_limit:
            break
    candidates.sort(key=lambda value: (-value["matched_word_count"], value["target_paragraph_index"], value["target_start"]))
    truncated = len(candidates) >= hard_limit
    selected = candidates[:max_matches]
    if len(candidates) > max_matches:
        truncated = True
    covered: dict[int, set[int]] = defaultdict(set)
    for value in selected:
        covered[value["target_paragraph_index"]].update(
            range(value["target_start"], value["target_start"] + value["matched_word_count"])
        )
        value.pop("target_start", None)
    return selected, sum(len(value) for value in covered.values()), truncated


class LocalPlagiarismService:
    def __init__(self, db: Session):
        self.db = db
        self.audit = AuditService(db)

    def queue_for_job(self, job: DocumentCheckJob, submission: TeacherDocumentSubmission) -> LocalPlagiarismRun:
        existing = self.db.scalar(select(LocalPlagiarismRun).where(
            LocalPlagiarismRun.organization_id == job.organization_id,
            LocalPlagiarismRun.job_id == job.id,
        ))
        if existing is not None:
            return existing
        run = LocalPlagiarismRun(
            organization_id=job.organization_id,
            job_id=job.id,
            target_submission_id=submission.id,
            status=DocumentCheckJobStatus.QUEUED,
            queued_at=job.queued_at,
            algorithm_version=ALGORITHM_VERSION,
            minimum_match_words=settings.LOCAL_PLAGIARISM_MIN_MATCH_WORDS,
            target_word_count=0,
            excluded_word_count=0,
            matched_word_count=0,
            similarity_percent=0,
            candidate_documents_available=0,
            candidate_documents_scanned=0,
            matches_count=0,
            matches_truncated=False,
        )
        self.db.add(run)
        self.db.flush()
        return run

    def mark_processing(self, job: DocumentCheckJob) -> None:
        if job.teacher_submission_id is None:
            return
        submission = self.db.scalar(select(TeacherDocumentSubmission).where(
            TeacherDocumentSubmission.organization_id == job.organization_id,
            TeacherDocumentSubmission.id == job.teacher_submission_id,
        ))
        if submission is None:
            return
        run = self.queue_for_job(job, submission)
        if run.status == DocumentCheckJobStatus.QUEUED:
            run.status = DocumentCheckJobStatus.PROCESSING
            run.started_at = datetime.now(UTC)
            run.finished_at = None
            run.error_code = None
            run.error_message = None
            self.db.flush()

    def _candidate_submissions(self, org_id: uuid.UUID, target_submission_id: uuid.UUID):
        base = (
            select(LocalPlagiarismIndex, TeacherDocumentSubmission)
            .join(
                TeacherDocumentSubmission,
                (TeacherDocumentSubmission.organization_id == LocalPlagiarismIndex.organization_id)
                & (TeacherDocumentSubmission.id == LocalPlagiarismIndex.submission_id),
            )
            .where(
                LocalPlagiarismIndex.organization_id == org_id,
                LocalPlagiarismIndex.submission_id != target_submission_id,
                ~TeacherDocumentSubmission.lifecycle.has(TeacherDocumentLifecycle.archived.is_(True)),
                ~TeacherDocumentSubmission.lifecycle.has(TeacherDocumentLifecycle.original_delete_requested_at.is_not(None)),
            )
        )
        available = int(self.db.scalar(select(func.count()).select_from(base.subquery())) or 0)
        rows = list(self.db.execute(
            base.order_by(LocalPlagiarismIndex.indexed_at.desc(), LocalPlagiarismIndex.submission_id.desc())
            .limit(settings.LOCAL_PLAGIARISM_MAX_CANDIDATE_DOCUMENTS)
        ).tuples().all())
        return available, rows

    def _index_target(self, submission: TeacherDocumentSubmission, extracted: dict[str, Any]) -> None:
        key = (submission.organization_id, submission.id)
        if self.db.get(LocalPlagiarismIndex, key) is not None:
            return
        index = LocalPlagiarismIndex(
            organization_id=submission.organization_id,
            submission_id=submission.id,
            algorithm_version=ALGORITHM_VERSION,
            eligible_word_count=extracted["eligible_word_count"],
            excluded_word_count=extracted["excluded_word_count"],
            paragraph_count=len(extracted["paragraphs"]),
            indexed_at=datetime.now(UTC),
        )
        self.db.add(index)
        self.db.flush()
        for item in extracted["paragraphs"]:
            self.db.add(LocalPlagiarismParagraph(
                organization_id=submission.organization_id,
                submission_id=submission.id,
                paragraph_index=item["paragraph_index"],
                normalized_text=item["normalized_text"],
                word_count=item["word_count"],
            ))
        self.db.flush()

    def prepare(self, job_id: uuid.UUID, worker_id: str, extracted: dict[str, Any], *,
                max_matches: int | None = None) -> dict[str, Any]:
        """Read and compare in a killable child, without locks or database writes."""
        run = self.db.scalar(select(LocalPlagiarismRun).where(
            LocalPlagiarismRun.job_id == job_id,
            LocalPlagiarismRun.status == DocumentCheckJobStatus.PROCESSING,
        ))
        job = self.db.scalar(select(DocumentCheckJob).where(
            DocumentCheckJob.id == job_id,
            DocumentCheckJob.status == DocumentCheckJobStatus.PROCESSING,
            DocumentCheckJob.worker_id == worker_id[:128],
        ))
        if run is None or job is None or job.teacher_submission_id is None:
            raise ValueError("Local similarity run is not owned by the current worker")
        submission = self.db.scalar(select(TeacherDocumentSubmission).where(
            TeacherDocumentSubmission.organization_id == job.organization_id,
            TeacherDocumentSubmission.id == job.teacher_submission_id,
        ))
        if submission is None:
            raise ValueError("Local similarity target submission is missing")
        available, candidates = self._candidate_submissions(job.organization_id, submission.id)
        candidate_ids = [index.submission_id for index, _ in candidates]
        source_rows: list[tuple[LocalPlagiarismParagraph, TeacherDocumentSubmission]] = []
        if candidate_ids:
            source_rows = list(self.db.execute(
                select(LocalPlagiarismParagraph, TeacherDocumentSubmission)
                .join(
                    TeacherDocumentSubmission,
                    (TeacherDocumentSubmission.organization_id == LocalPlagiarismParagraph.organization_id)
                    & (TeacherDocumentSubmission.id == LocalPlagiarismParagraph.submission_id),
                )
                .where(
                    LocalPlagiarismParagraph.organization_id == job.organization_id,
                    LocalPlagiarismParagraph.submission_id.in_(candidate_ids),
                )
                .order_by(LocalPlagiarismParagraph.submission_id, LocalPlagiarismParagraph.paragraph_index)
            ).tuples().all())
        matches, matched_words, matches_truncated = find_local_similarity_matches(
            extracted["paragraphs"], source_rows,
            minimum_match_words=run.minimum_match_words,
            max_matches=settings.LOCAL_PLAGIARISM_MAX_MATCHES if max_matches is None else max_matches,
        )
        return {
            "job_id": job_id, "run_id": run.id, "extracted": extracted,
            "matches": matches, "matched_words": matched_words,
            "matches_truncated": matches_truncated, "available": available,
            "scanned": len(candidates),
        }

    def _owned_job(self, job_id: uuid.UUID, worker_id: str) -> DocumentCheckJob | None:
        # Match the queue's lock order: job first, then similarity run. Recovery
        # must not reassign a lease while a result is being committed.
        from app.services.document_check_job_service import DocumentCheckJobService
        return DocumentCheckJobService(self.db).lock_owned_job(job_id, worker_id)

    def complete(self, job_id: uuid.UUID, worker_id: str, extracted: dict[str, Any]) -> None:
        """Synchronous service entry point; the worker uses the two stages separately."""
        self.complete_prepared(job_id, worker_id, self.prepare(job_id, worker_id, extracted))

    def complete_prepared(self, job_id: uuid.UUID, worker_id: str, prepared: dict[str, Any]) -> None:
        job = self._owned_job(job_id, worker_id)
        if job is None or job.teacher_submission_id is None or prepared["job_id"] != job_id:
            raise ValueError("Local similarity result is not owned by the current worker")
        run = self.db.scalar(select(LocalPlagiarismRun).where(
            LocalPlagiarismRun.organization_id == job.organization_id,
            LocalPlagiarismRun.job_id == job.id,
            LocalPlagiarismRun.id == prepared["run_id"],
            LocalPlagiarismRun.status == DocumentCheckJobStatus.PROCESSING,
        ).with_for_update().execution_options(populate_existing=True))
        if run is None:
            raise ValueError("Local similarity run is no longer processing")
        submission = self.db.scalar(select(TeacherDocumentSubmission).where(
            TeacherDocumentSubmission.organization_id == job.organization_id,
            TeacherDocumentSubmission.id == job.teacher_submission_id,
        ))
        if submission is None:
            raise ValueError("Local similarity target submission is missing")
        extracted = prepared["extracted"]
        matches = prepared["matches"]
        matched_words = prepared["matched_words"]
        self._index_target(submission, extracted)
        for sequence, item in enumerate(matches, 1):
            self.db.add(LocalPlagiarismMatch(
                organization_id=job.organization_id,
                run_id=run.id,
                sequence=sequence,
                source_submission_id=item["source_submission_id"],
                target_paragraph_index=item["target_paragraph_index"],
                source_paragraph_index=item["source_paragraph_index"],
                matched_word_count=item["matched_word_count"],
                target_excerpt=item["target_excerpt"],
                source_excerpt=item["source_excerpt"],
            ))
        run.target_word_count = extracted["eligible_word_count"]
        run.excluded_word_count = extracted["excluded_word_count"]
        run.matched_word_count = matched_words
        run.similarity_percent = round((matched_words / run.target_word_count * 100) if run.target_word_count else 0, 2)
        run.candidate_documents_available = prepared["available"]
        run.candidate_documents_scanned = prepared["scanned"]
        run.matches_count = len(matches)
        run.matches_truncated = prepared["matches_truncated"]
        run.status = DocumentCheckJobStatus.COMPLETED
        run.finished_at = datetime.now(UTC)
        run.error_code = None
        run.error_message = None
        self.audit.record(
            organization_id=job.organization_id,
            actor_user_id=None,
            event_type=AuditEventType.LOCAL_PLAGIARISM_RUN_COMPLETED,
            entity_type="local_plagiarism_run",
            entity_id=run.id,
            metadata={
                "matched_word_count": matched_words,
                "similarity_percent": float(run.similarity_percent),
                "candidate_documents_scanned": prepared["scanned"],
                "matches_count": len(matches),
            },
        )
        self.db.flush()

    def fail_analysis(self, job_id: uuid.UUID, worker_id: str) -> None:
        job = self._owned_job(job_id, worker_id)
        if job is None:
            return
        run = self.db.scalar(select(LocalPlagiarismRun).where(
            LocalPlagiarismRun.organization_id == job.organization_id,
            LocalPlagiarismRun.job_id == job_id,
            LocalPlagiarismRun.status == DocumentCheckJobStatus.PROCESSING,
        ).with_for_update())
        if run is None:
            return
        run.status = DocumentCheckJobStatus.FAILED
        run.finished_at = datetime.now(UTC)
        run.error_code = SAFE_ERROR_CODE
        run.error_message = SAFE_ERROR_MESSAGE
        self.audit.record(
            organization_id=run.organization_id,
            actor_user_id=None,
            event_type=AuditEventType.LOCAL_PLAGIARISM_RUN_FAILED,
            entity_type="local_plagiarism_run",
            entity_id=run.id,
            metadata={"error_code": SAFE_ERROR_CODE},
        )
        self.db.flush()

    def retry_or_fail_with_job(self, job: DocumentCheckJob) -> None:
        run = self.db.scalar(select(LocalPlagiarismRun).where(
            LocalPlagiarismRun.organization_id == job.organization_id,
            LocalPlagiarismRun.job_id == job.id,
        ).with_for_update())
        if run is None:
            return
        if job.status == DocumentCheckJobStatus.QUEUED:
            run.status = DocumentCheckJobStatus.QUEUED
            run.started_at = None
            run.finished_at = None
            run.error_code = None
            run.error_message = None
        elif job.status == DocumentCheckJobStatus.FAILED:
            run.status = DocumentCheckJobStatus.FAILED
            run.finished_at = job.finished_at or datetime.now(UTC)
            run.error_code = job.error_code or SAFE_ERROR_CODE
            run.error_message = job.error_message or SAFE_ERROR_MESSAGE
            self.audit.record(
                organization_id=run.organization_id,
                actor_user_id=None,
                event_type=AuditEventType.LOCAL_PLAGIARISM_RUN_FAILED,
                entity_type="local_plagiarism_run",
                entity_id=run.id,
                metadata={"error_code": run.error_code},
            )
        self.db.flush()

    def list_runs(self, submission: TeacherDocumentSubmission, offset: int, limit: int) -> tuple[list[LocalPlagiarismRun], int]:
        query = select(LocalPlagiarismRun).where(
            LocalPlagiarismRun.organization_id == submission.organization_id,
            LocalPlagiarismRun.target_submission_id == submission.id,
        )
        total = int(self.db.scalar(select(func.count()).select_from(query.subquery())) or 0)
        items = list(self.db.scalars(query.order_by(
            LocalPlagiarismRun.queued_at.desc(), LocalPlagiarismRun.id.desc()
        ).offset(offset).limit(limit)))
        return items, total

    def get_run(self, submission: TeacherDocumentSubmission, run_id: uuid.UUID) -> LocalPlagiarismRun:
        run = self.db.scalar(select(LocalPlagiarismRun).where(
            LocalPlagiarismRun.organization_id == submission.organization_id,
            LocalPlagiarismRun.target_submission_id == submission.id,
            LocalPlagiarismRun.id == run_id,
        ))
        if run is None:
            from fastapi import HTTPException
            raise HTTPException(404, detail="Local similarity result not found")
        return run

    def list_matches(
        self, run: LocalPlagiarismRun, teacher_id: uuid.UUID, offset: int, limit: int,
    ) -> tuple[list[tuple[LocalPlagiarismMatch, TeacherDocumentSubmission]], int]:
        query = (
            select(LocalPlagiarismMatch, TeacherDocumentSubmission)
            .join(
                TeacherDocumentSubmission,
                (TeacherDocumentSubmission.organization_id == LocalPlagiarismMatch.organization_id)
                & (TeacherDocumentSubmission.id == LocalPlagiarismMatch.source_submission_id),
            )
            .where(
                LocalPlagiarismMatch.organization_id == run.organization_id,
                LocalPlagiarismMatch.run_id == run.id,
            )
        )
        total = int(self.db.scalar(select(func.count()).select_from(query.subquery())) or 0)
        return list(self.db.execute(query.order_by(
            LocalPlagiarismMatch.sequence
        ).offset(offset).limit(limit)).tuples().all()), total
