import io
import uuid
import zipfile
from types import SimpleNamespace

import pytest

from app.services.local_plagiarism_service import (
    extract_local_similarity_paragraphs,
    find_local_similarity_matches,
)


W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _source_paragraph(text: str, paragraph_index: int = 1):
    return SimpleNamespace(normalized_text=text, paragraph_index=paragraph_index)


def _submission():
    return SimpleNamespace(id=uuid.uuid4())


def _docx(document: str, styles: str = "") -> io.BytesIO:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as package:
        package.writestr("word/document.xml", document)
        package.writestr("word/styles.xml", styles or f'<w:styles xmlns:w="{W}"/>')
    output.seek(0)
    return output


def test_exact_partial_copy_reports_one_maximal_match_and_unique_target_words():
    target = [{
        "paragraph_index": 7,
        "normalized_text": "в процессе производственной практики студент анализирует требования и документирует результаты работы",
    }]
    source = _source_paragraph(
        "перед защитой в процессе производственной практики студент анализирует требования и документирует результаты работы руководителю",
        3,
    )
    submission = _submission()

    matches, matched_words, truncated = find_local_similarity_matches(
        target, [(source, submission)], minimum_match_words=8, max_matches=20,
    )

    assert truncated is False
    assert len(matches) == 1
    assert matches[0]["source_submission_id"] == submission.id
    assert matches[0]["target_paragraph_index"] == 7
    assert matches[0]["source_paragraph_index"] == 3
    assert matches[0]["matched_word_count"] == 11
    assert matched_words == 11


def test_short_common_sequence_is_not_reported():
    target = [{"paragraph_index": 1, "normalized_text": "студент подготовил итоговый отчет по практике"}]
    source = _source_paragraph("студент подготовил итоговый отчет по практике для кафедры")

    matches, matched_words, truncated = find_local_similarity_matches(
        target, [(source, _submission())], minimum_match_words=8, max_matches=20,
    )

    assert matches == []
    assert matched_words == 0
    assert truncated is False


def test_extractor_omits_headings_quotes_and_bibliography():
    document = f'''<w:document xmlns:w="{W}"><w:body>
      <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Введение</w:t></w:r></w:p>
      <w:p><w:r><w:t>Это собственный аналитический текст студента о выполненной практике и полученных результатах.</w:t></w:r></w:p>
      <w:p><w:pPr><w:pStyle w:val="Quote"/></w:pPr><w:r><w:t>Цитата которая не должна попадать в сравнение даже если она длинная и подробная.</w:t></w:r></w:p>
      <w:p><w:r><w:t>Список литературы</w:t></w:r></w:p>
      <w:p><w:r><w:t>Иванов И И Методические рекомендации Москва 2025</w:t></w:r></w:p>
    </w:body></w:document>'''
    styles = f'''<w:styles xmlns:w="{W}">
      <w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="Heading 1"/></w:style>
      <w:style w:type="paragraph" w:styleId="Quote"><w:name w:val="Quote"/></w:style>
    </w:styles>'''

    extracted = extract_local_similarity_paragraphs(_docx(document, styles), max_words=10_000)

    assert len(extracted["paragraphs"]) == 1
    assert extracted["paragraphs"][0]["paragraph_index"] == 2
    assert "собственный аналитический текст" in extracted["paragraphs"][0]["normalized_text"]
    assert extracted["excluded_word_count"] > 0


@pytest.mark.parametrize("stage", ["_stage_and_analyze_child", "_similarity_child"])
@pytest.mark.parametrize("failure", ["timeout", "lease_lost", "stopped"])
def test_worker_supervises_both_stages_and_terminates_children(monkeypatch, stage, failure):
    from contextlib import nullcontext
    from queue import Empty
    from app.workers import document_check_worker as module

    clock = [0.0]
    heartbeats = []

    class ResultQueue:
        closed = False

        def get_nowait(self):
            raise Empty

        def close(self):
            self.closed = True

    class HungProcess:
        alive = False
        terminated = False

        def start(self):
            self.alive = True

        def is_alive(self):
            return self.alive

        def join(self, timeout=None):
            clock[0] += timeout or 0
            if failure == "stopped":
                worker.stopping = True

        def terminate(self):
            self.terminated = True
            self.alive = False

        def kill(self):
            self.alive = False

    result_queue = ResultQueue()
    process = HungProcess()
    context = SimpleNamespace(Queue=lambda **_: result_queue, Process=lambda **_: process)
    monkeypatch.setattr(module.multiprocessing, "get_context", lambda _: context)
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(module.settings, "DOCUMENT_CHECK_WORKER_TIMEOUT_SECONDS", 1)

    def heartbeat(_service, job_id, worker_id):
        heartbeats.append((job_id, worker_id))
        return failure != "lease_lost"

    monkeypatch.setattr(module.DocumentCheckJobService, "heartbeat", heartbeat)
    session = SimpleNamespace(execute=lambda *_: None)
    worker = module.DocumentCheckWorker(lambda: nullcontext(session), worker_id="supervised")
    if failure == "lease_lost":
        with pytest.raises(module._LeaseLost):
            worker._run_child(uuid.uuid4(), getattr(module, stage), ())
    else:
        outcome = worker._run_child(uuid.uuid4(), getattr(module, stage), ())
        expected = "CHECK_ANALYSIS_TIMEOUT" if failure == "timeout" else "CHECK_WORKER_STOPPED"
        assert outcome == ("error", expected)
    assert process.terminated and not process.alive
    assert result_queue.closed
    if failure != "stopped":
        assert heartbeats
