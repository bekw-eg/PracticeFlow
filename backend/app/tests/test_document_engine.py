from app.documents.defaults import build_default_document
from app.documents.numbering import compute_numbering
from app.documents.schemas import (
    DocumentModel,
    HeadingBlock,
    ParagraphBlock,
    Section,
    TableBlock,
    TableCell,
    TableRow,
    TextRun,
    VariableRun,
)
from app.documents.validators import required_sections_present, validate_document
from app.documents.variables import VariableContext, resolve_document


def test_default_document_has_required_sections_and_title_page():
    doc = build_default_document()
    assert doc.title_page is not None
    assert len(doc.sections) == 6
    assert all(s.required for s in doc.sections)


def test_default_document_passes_validation():
    doc = build_default_document()
    assert validate_document(doc) == []


def test_document_round_trips_through_json():
    doc = build_default_document()
    dumped = doc.model_dump(mode="json")
    restored = DocumentModel.model_validate(dumped)
    assert restored.sections[0].title == doc.sections[0].title
    assert restored.sections[0].blocks[0].id == doc.sections[0].blocks[0].id


def test_node_ids_are_unique_and_not_index_based():
    doc = DocumentModel()
    doc.sections = [
        Section(title="A", blocks=[ParagraphBlock(runs=[TextRun(text="x")])]),
        Section(title="B", blocks=[ParagraphBlock(runs=[TextRun(text="y")])]),
    ]
    id_a = doc.sections[0].blocks[0].id
    id_b = doc.sections[1].blocks[0].id
    assert id_a != id_b
    assert not id_a.isdigit()


def test_validator_catches_duplicate_node_ids():
    doc = DocumentModel()
    shared_block = ParagraphBlock(id="p_shared", runs=[TextRun(text="dup")])
    doc.sections = [
        Section(title="A", blocks=[shared_block]),
        Section(title="B", blocks=[ParagraphBlock(id="p_shared", runs=[TextRun(text="dup2")])]),
    ]
    errors = validate_document(doc)
    assert any("p_shared" in e for e in errors)


def test_validator_catches_unknown_variable_key():
    doc = DocumentModel()
    doc.sections = [Section(title="A", blocks=[ParagraphBlock(runs=[VariableRun(key="not.a.real.variable")])])]
    errors = validate_document(doc)
    assert any("not.a.real.variable" in e for e in errors)


def test_validator_catches_negative_margins():
    doc = DocumentModel()
    doc.meta.margins.left_mm = -5
    errors = validate_document(doc)
    assert any("поле" in e for e in errors)


def test_required_sections_present_detects_missing_section():
    original = build_default_document()
    candidate = original.model_copy(deep=True)
    candidate.sections = candidate.sections[1:]  # drop the first required section
    errors = required_sections_present(original, candidate)
    assert len(errors) == 1


# --- Numbering (rule 12: matches the spec's own worked examples) ---


def test_numbering_matches_spec_example_start_at_2():
    doc = DocumentModel()
    doc.meta.numbering.start_number = 2
    doc.sections = [
        Section(
            title="Introduction",
            blocks=[
                HeadingBlock(level=1, runs=[TextRun(text="Purpose")]),
                HeadingBlock(level=1, runs=[TextRun(text="Scope")]),
            ],
        ),
        Section(title="Chapter", blocks=[]),
    ]
    numbers = compute_numbering(doc)
    intro, chapter = doc.sections
    assert numbers[intro.id] == "2"
    assert numbers[intro.blocks[0].id] == "2.1"
    assert numbers[intro.blocks[1].id] == "2.2"
    assert numbers[chapter.id] == "3"


def test_numbering_matches_spec_example_start_at_8():
    doc = DocumentModel()
    doc.meta.numbering.start_number = 8
    doc.sections = [Section(title="A"), Section(title="B")]
    numbers = compute_numbering(doc)
    assert numbers[doc.sections[0].id] == "8"
    assert numbers[doc.sections[1].id] == "9"


def test_numbering_skips_sections_and_headings_not_participating():
    doc = DocumentModel()
    doc.sections = [
        Section(title="Skip me", numbering={"participates": False}),
        Section(title="Count me"),
    ]
    numbers = compute_numbering(doc)
    assert doc.sections[0].id not in numbers
    assert numbers[doc.sections[1].id] == "1"


def test_numbering_disabled_globally_produces_no_numbers():
    doc = DocumentModel()
    doc.meta.numbering.enabled = False
    doc.sections = [Section(title="A")]
    assert compute_numbering(doc) == {}


# --- Variable resolution ---


def test_resolve_document_populates_resolved_text_without_mutating_key():
    doc = DocumentModel()
    doc.sections = [Section(title="A", blocks=[ParagraphBlock(runs=[VariableRun(key="student.full_name")])])]
    ctx = VariableContext(student_full_name="Иванов Иван")
    resolved = resolve_document(doc, ctx)

    resolved_run = resolved.sections[0].blocks[0].runs[0]
    assert resolved_run.resolved_text == "Иванов Иван"
    assert resolved_run.key == "student.full_name"
    # Original document is untouched.
    original_run = doc.sections[0].blocks[0].runs[0]
    assert original_run.resolved_text is None


def test_resolve_document_walks_into_tables():
    doc = DocumentModel()
    table = TableBlock(rows=[TableRow(cells=[TableCell(blocks=[ParagraphBlock(runs=[VariableRun(key="academic_year")])])])])
    doc.sections = [Section(title="A", blocks=[table])]
    ctx = VariableContext(academic_year="2025-2026")
    resolved = resolve_document(doc, ctx)
    cell_run = resolved.sections[0].blocks[0].rows[0].cells[0].blocks[0].runs[0]
    assert cell_run.resolved_text == "2025-2026"


def test_resolve_document_unknown_key_falls_back_to_placeholder():
    doc = DocumentModel()
    doc.sections = [Section(title="A", blocks=[ParagraphBlock(runs=[VariableRun(key="nonexistent.key")])])]
    resolved = resolve_document(doc, VariableContext())
    assert resolved.sections[0].blocks[0].runs[0].resolved_text == "{{nonexistent.key}}"
