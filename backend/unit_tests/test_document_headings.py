import io
import zipfile

from app.models.enums import CheckRuleType
from app.schemas.document_check import validate_rule_config
from app.services.document_analyzer import NS, W, _Styles, _xml, analyze_document
from app.services.document_paragraphs import classify_paragraphs, inspect_paragraphs
from app.services.docx_html_preview import render_docx_html
from test_document_analyzer import _rule


def package(body, styles="", title=True):
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w") as archive:
        cover = '<w:p><w:r><w:t>Title</w:t><w:br w:type="page"/></w:r></w:p>' if title else ""
        archive.writestr("word/document.xml", f'<w:document xmlns:w="{W}"><w:body>{cover}{body}<w:sectPr/></w:body></w:document>')
        archive.writestr("word/styles.xml", f'''<w:styles xmlns:w="{W}"><w:docDefaults><w:rPrDefault>
          <w:rPr><w:rFonts w:ascii="Times New Roman"/><w:sz w:val="28"/></w:rPr>
          </w:rPrDefault></w:docDefaults>{styles}</w:styles>''')
    result.seek(0)
    return result


def body_rule():
    return _rule(CheckRuleType.FONTS_SIZES, {"allowed_fonts": ["Times New Roman"], "min_size_pt": 14, "max_size_pt": 14})


def heading_rule(level=1):
    return _rule(CheckRuleType.HEADINGS, {"levels": [{"level": level, "allowed_fonts": ["Times New Roman"],
        "min_size_pt": 16, "max_size_pt": 16, "bold": True, "alignment": "CENTER", "space_before_pt": 12}], "require_numbering": False})


HEADING_STYLES = '''<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/>
  <w:pPr><w:outlineLvl w:val="0"/><w:spacing w:before="240"/></w:pPr>
  <w:rPr><w:b/><w:sz w:val="32"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="CustomChapter"><w:basedOn w:val="Heading1"/></w:style>'''


def test_inherited_heading_with_wrong_alignment_is_not_checked_as_body():
    source = package('<w:p><w:pPr><w:pStyle w:val="CustomChapter"/><w:jc w:val="left"/>'
                     '<w:spacing w:after="80"/></w:pPr><w:r><w:t>Not a familiar title</w:t></w:r></w:p>', HEADING_STYLES)
    body, heading = body_rule(), heading_rule()
    findings, summary = analyze_document(source, [body, heading], max_findings=100)
    assert summary["rules_evaluated"] == 2
    assert len(findings) == 1
    assert findings[0].check_rule_id == heading.id
    assert findings[0].code == "PARAGRAPH_ALIGNMENT_MISMATCH"
    assert findings[0].location["paragraph_index"] == 2
    assert findings[0].location["paragraph_type"] == "HEADING_1"
    assert findings[0].expected == {"value": "CENTER"}
    assert findings[0].actual == {"value": "LEFT"}
    source.seek(0)
    html = render_docx_html(source).html
    assert "text-align:left" in html and "margin-top:12.0pt" in html
    assert 'data-paragraph-index="2"' in html


def test_manual_override_applies_to_entire_paragraph_across_page_breaks():
    source = package('<w:p><w:pPr><w:pStyle w:val="CustomChapter"/></w:pPr><w:r>'
                     '<w:t>First half</w:t><w:br w:type="page"/><w:t>Second half</w:t></w:r></w:p>', HEADING_STYLES)
    body, heading = body_rule(), heading_rule()
    findings, _ = analyze_document(source, [body, heading], max_findings=100, paragraph_overrides={"2": "BODY"})
    assert findings and all(f.check_rule_id == body.id for f in findings)
    assert all(f.location["paragraph_type"] == "BODY" for f in findings)
    source.seek(0)
    parsed = inspect_paragraphs(source, {"2": "BODY"})
    assert parsed[1]["automatic_type"] == "HEADING_1"
    assert parsed[1]["paragraph_type"] == "BODY" and parsed[1]["source"] == "MANUAL"


def test_named_numbered_and_caption_list_heuristics():
    texts = ["Введение", "Қорытынды", "Conclusion", "1.1 Scope", "1.1.1 Details", "1. Buy supplies",
             "Рисунок 1 — схема", "Таблица 2. Данные", "1-сурет. Сызба", "Just a short paragraph"]
    source = package("".join(f'<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:b/></w:rPr><w:t>{text}</w:t></w:r></w:p>' for text in texts))
    actual = [p["paragraph_type"] for p in inspect_paragraphs(source)][1:]
    assert actual == ["HEADING_1", "HEADING_1", "HEADING_1", "HEADING_2", "HEADING_3", "BODY", "BODY", "BODY", "BODY", "BODY"]


def test_direct_outline_and_manual_override_take_priority():
    document = _xml(f'<w:document xmlns:w="{W}"><w:body><w:p><w:pPr><w:outlineLvl w:val="2"/></w:pPr><w:r><w:t>Text</w:t></w:r></w:p></w:body></w:document>'.encode())
    resolver = _Styles(None, None)
    assert classify_paragraphs(document, resolver)[0]["paragraph_type"] == "HEADING_3"
    assert classify_paragraphs(document, resolver, {"1": "BODY"})[0]["paragraph_type"] == "BODY"
    document.find(".//w:outlineLvl", NS).set(f"{{{W}}}val", "9")
    assert classify_paragraphs(document, resolver)[0]["paragraph_type"] == "BODY"


def test_custom_short_bold_large_title_is_recognized_even_left_aligned():
    source = package('<w:p><w:pPr><w:jc w:val="left"/></w:pPr><w:r><w:rPr><w:b/><w:sz w:val="32"/></w:rPr>'
                     '<w:t>Unusual chapter title</w:t></w:r></w:p><w:p><w:r><w:t>'
                     + 'Long ordinary body paragraph. ' * 20 + '</w:t></w:r></w:p>')
    items = inspect_paragraphs(source)
    assert items[1]["paragraph_type"] == "HEADING_1"
    source.seek(0)
    findings, _ = analyze_document(source, [body_rule(), heading_rule()], max_findings=100)
    assert any(f.code == "PARAGRAPH_ALIGNMENT_MISMATCH" and f.location["paragraph_type"] == "HEADING_1" for f in findings)


def test_cover_boundary_unknown_and_empty_content_do_not_claim_success():
    for source, expected in [(package('<w:p><w:r><w:t>Введение</w:t></w:r></w:p>', title=False), "BOUNDARY_UNKNOWN"),
                             (package(""), "NO_CONTENT")]:
        findings, summary = analyze_document(source, [heading_rule()], max_findings=100, paragraph_overrides={"1": "HEADING_1"})
        assert findings == [] and summary["rules_evaluated"] == 0
        assert summary["first_page_exclusion"] == expected


def test_centering_supports_but_does_not_replace_other_heading_evidence():
    source = package('<w:p><w:pPr><w:jc w:val="center"/><w:keepNext/></w:pPr>'
                     '<w:r><w:rPr><w:b/></w:rPr><w:t>Custom section title</w:t></w:r></w:p>'
                     '<w:p><w:pPr><w:jc w:val="center"/></w:pPr>'
                     '<w:r><w:rPr><w:b/></w:rPr><w:t>Short ordinary text</w:t></w:r></w:p>'
                     '<w:p><w:pPr><w:jc w:val="center"/><w:keepNext/></w:pPr>'
                     '<w:r><w:t>Another ordinary paragraph</w:t></w:r></w:p>')
    assert [p["paragraph_type"] for p in inspect_paragraphs(source)][1:] == ["HEADING_1", "BODY", "BODY"]


def test_old_heading_config_stays_compatible_without_adding_requirements():
    old = {"levels": [{"level": 1, "min_size_pt": 14, "max_size_pt": 16}], "require_numbering": False}
    normalized = validate_rule_config(CheckRuleType.HEADINGS, 1, old)
    assert normalized["levels"][0]["alignment"] is None
    assert normalized["levels"][0]["allowed_fonts"] is None
    assert old["levels"][0] == {"level": 1, "min_size_pt": 14, "max_size_pt": 16}
