import pytest
from pydantic import ValidationError

from app.models.enums import CheckRuleType
from app.schemas.document_check import DocumentPageExclusions
from app.services.document_analyzer import analyze_document
from app.services.document_page_exclusions import validate_preview_locations
from app.services.docx_html_preview import render_docx_html
from test_document_analyzer import _rule
from test_document_headings import package


def example():
    return package('<w:p><w:r><w:t>Shared body text</w:t><w:br w:type="page"/>'
                   '<w:t>Continuation</w:t></w:r><w:r><w:t>Only on page two</w:t></w:r></w:p>'
                   '<w:p><w:r><w:t>Only on page three</w:t></w:r></w:p>')


def exclusions(pages):
    return {"pages": pages, "layout": [
        {"number": 1, "section_index": 1, "paragraphs": {"1": []}},
        {"number": 2, "section_index": 1, "paragraphs": {"2": [1, 2]}},
        {"number": 3, "section_index": 1, "paragraphs": {"2": [1], "3": [1]}},
    ]}


def test_excluded_page_keeps_shared_paragraph_and_run_on_included_page():
    fonts = _rule(CheckRuleType.FONTS_SIZES, {"allowed_fonts": ["Arial"], "min_size_pt": 14, "max_size_pt": 14})
    indents = _rule(CheckRuleType.PARAGRAPH_SPACING_INDENTS, {"first_line_indent_mm": 12.5})
    findings, summary = analyze_document(example(), [fonts, indents], max_findings=100, page_exclusions=exclusions([2]))
    assert summary["excluded_pages"] == [2]
    assert findings and all(f.location["pages"] == [3] for f in findings)
    assert not any(f.location.get("paragraph_index") == 2 and f.location.get("run_index") == 2 for f in findings)
    assert any(f.location.get("paragraph_index") == 2 and f.location.get("run_index") == 1 for f in findings)
    assert any(f.location.get("paragraph_index") == 3 for f in findings)


def test_exclusions_apply_before_finding_limit_and_restore_when_removed():
    rule = _rule(CheckRuleType.FONTS_SIZES, {"allowed_fonts": ["Arial"], "min_size_pt": 14, "max_size_pt": 14})
    findings, summary = analyze_document(example(), [rule], max_findings=1, page_exclusions=exclusions([2, 3]))
    assert findings == [] and summary["findings_truncated"] is False
    findings, _ = analyze_document(example(), [rule], max_findings=100)
    assert len(findings) == 3


def test_page_format_errors_only_apply_to_nonexcluded_content_pages():
    rule = _rule(CheckRuleType.PAGE_FORMAT_MARGINS, {"page_size": "A4", "orientation": "PORTRAIT",
        "margins": {"top_mm": 20, "right_mm": 10, "bottom_mm": 20, "left_mm": 30}})
    findings, _ = analyze_document(example(), [rule], max_findings=100, page_exclusions=exclusions([2]))
    assert findings and all(f.location["pages"] == [3] for f in findings)
    findings, _ = analyze_document(example(), [rule], max_findings=100, page_exclusions=exclusions([2, 3]))
    assert findings == []


def test_preview_location_validation_requires_complete_map_and_valid_source_indexes():
    preview = render_docx_html(example())
    valid = DocumentPageExclusions.model_validate(exclusions([2]))
    validate_preview_locations(valid, preview.html)
    for change in (lambda e: e.layout[1].paragraphs.update({"999": [1]}),
                   lambda e: e.layout[1].paragraphs.update({"2": [999]}),
                   lambda e: e.layout[2].paragraphs.pop("3")):
        invalid = valid.model_copy(deep=True)
        change(invalid)
        with pytest.raises(ValueError):
            validate_preview_locations(invalid, preview.html)


@pytest.mark.parametrize("pages", [[0], [-1], [2001], [True], [2, 2], [4]])
def test_page_numbers_are_bounded_strict_and_belong_to_preview(pages):
    with pytest.raises(ValidationError):
        DocumentPageExclusions.model_validate(exclusions(pages))


def test_empty_exclusions_remain_backward_compatible_and_partial_layout_is_rejected():
    assert DocumentPageExclusions.model_validate({}).pages == []
    invalid = exclusions([2])
    invalid["layout"].pop(0)
    with pytest.raises(ValidationError):
        DocumentPageExclusions.model_validate(invalid)
