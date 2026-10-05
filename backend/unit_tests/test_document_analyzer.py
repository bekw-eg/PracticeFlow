import io
import json
import uuid
import zipfile

from app.models.enums import CheckRuleSeverity, CheckRuleType
from app.services.document_analyzer import ANALYZER_VERSION, AnalyzerRule, analyze_document

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _docx(*, font="Arial", size_half_points=24, body="PRIVATE STUDENT TEXT", landscape=False):
    width, height = ((16838, 11906) if landscape else (11906, 16838))
    orientation = ' w:orient="landscape"' if landscape else ""
    document = f'''<w:document xmlns:w="{W}"><w:body>
      <w:p><w:r><w:rPr><w:rFonts w:ascii="Title Font"/><w:sz w:val="60"/></w:rPr>
        <w:t>TITLE PAGE</w:t><w:br w:type="page"/></w:r></w:p>
      <w:p><w:pPr><w:spacing w:before="0" w:after="0" w:line="360" w:lineRule="auto"/>
        <w:ind w:firstLine="567" w:left="0" w:right="0"/></w:pPr>
        <w:r><w:t>{body}</w:t></w:r></w:p>
      <w:sectPr><w:pgSz w:w="{width}" w:h="{height}"{orientation}/>
        <w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr>
    </w:body></w:document>'''
    styles = f'''<w:styles xmlns:w="{W}"><w:docDefaults>
      <w:rPrDefault><w:rPr><w:rFonts w:ascii="{font}" w:hAnsi="{font}"/><w:sz w:val="{size_half_points}"/></w:rPr></w:rPrDefault>
    </w:docDefaults></w:styles>'''
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as package:
        package.writestr("word/document.xml", document)
        package.writestr("word/styles.xml", styles)
    output.seek(0)
    return output


def _rule(rule_type, config):
    return AnalyzerRule(
        id=uuid.uuid4(), rule_type=rule_type, category="formatting",
        severity=CheckRuleSeverity.ERROR, config=config,
    )


def _rules():
    return [
        _rule(CheckRuleType.PAGE_FORMAT_MARGINS, {
            "page_size": "A4", "orientation": "PORTRAIT",
            "margins": {"top_mm": 25.4, "right_mm": 25.4, "bottom_mm": 25.4, "left_mm": 25.4},
            "width_mm": None, "height_mm": None,
        }),
        _rule(CheckRuleType.FONTS_SIZES, {
            "allowed_fonts": ["Arial"], "min_size_pt": 12.0, "max_size_pt": 12.0,
        }),
        _rule(CheckRuleType.PARAGRAPH_SPACING_INDENTS, {
            "line_spacing": 1.5, "space_before_pt": 0.0, "space_after_pt": 0.0,
            "first_line_indent_mm": 10.0, "left_indent_mm": 0.0, "right_indent_mm": 0.0,
        }),
    ]


def test_compliant_document_and_unsupported_rule_are_reported_truthfully():
    unsupported = _rule(CheckRuleType.TABLES, {"require_header_row": True, "require_caption": False,
                                              "caption_position": "ABOVE", "allowed_alignments": ["LEFT"]})
    findings, summary = analyze_document(_docx(), [*_rules(), unsupported], max_findings=100)
    assert findings == []
    assert summary == {
        "analyzer_version": ANALYZER_VERSION,
        "rules_total": 4,
        "rules_evaluated": 3,
        "rules_skipped": 1,
        "findings_count": 0,
        "findings_truncated": False,
        "first_page_exclusion": "APPLIED",
    }


def test_structural_mismatches_have_bounded_locations_without_document_text():
    findings, summary = analyze_document(_docx(font="Times New Roman", size_half_points=18, body="NEVER STORE ME", landscape=True), _rules(), max_findings=100)
    codes = {finding.code for finding in findings}
    assert {"PAGE_ORIENTATION_MISMATCH", "PAGE_SIZE_MISMATCH", "FONT_NOT_ALLOWED", "FONT_SIZE_OUT_OF_RANGE"} <= codes
    assert summary["findings_count"] == len(findings)
    serialized = json.dumps([finding.as_dict() for finding in findings])
    assert "NEVER STORE ME" not in serialized
    assert len(serialized) < 20_000
    assert all(set(finding.location) <= {"part", "section_index", "paragraph_index", "run_index", "paragraph_type"} for finding in findings)


def test_finding_cap_is_enforced_and_untrusted_font_name_is_bounded():
    findings, summary = analyze_document(_docx(font="X" * 10_000, size_half_points=2, landscape=True), _rules(), max_findings=2)
    assert len(findings) == 2
    assert summary["findings_count"] == 2
    assert summary["findings_truncated"] is True
    assert all(len(str(finding.actual)) < 500 for finding in findings)
