"""Read-only OOXML analyzer for the first executable document-check rules."""
from __future__ import annotations

import math
import uuid
import zipfile
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, BinaryIO

from lxml import etree

from app.models.enums import CheckRuleSeverity, CheckRuleType, EXECUTABLE_CHECK_RULE_TYPES

ANALYZER_VERSION = "phase-2.4.0"
FINDING_SCHEMA_VERSION = 1
SUPPORTED_RULE_TYPES = EXECUTABLE_CHECK_RULE_TYPES
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS = {"w": W, "a": A}
PAGE_SIZES_MM = {"A4": (210.0, 297.0), "LETTER": (215.9, 279.4), "LEGAL": (215.9, 355.6)}


@dataclass(frozen=True)
class AnalyzerRule:
    id: uuid.UUID
    rule_type: CheckRuleType
    category: str
    severity: CheckRuleSeverity
    config: dict[str, Any]


@dataclass(frozen=True)
class AnalyzerFinding:
    check_rule_id: uuid.UUID
    rule_type: CheckRuleType
    category: str
    severity: CheckRuleSeverity
    code: str
    property_name: str
    location: dict[str, Any]
    expected: dict[str, Any]
    actual: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "check_rule_id": str(self.check_rule_id), "rule_type": self.rule_type.value,
            "category": self.category, "severity": self.severity.value, "code": self.code,
            "property_name": self.property_name, "location": self.location,
            "expected": self.expected, "actual": self.actual,
        }


def _xml(payload: bytes) -> etree._Element:
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False)
    root = etree.fromstring(payload, parser=parser)
    if root.getroottree().docinfo.doctype:
        raise ValueError("unsupported OOXML declaration")
    return root


def _attr(node: etree._Element | None, name: str) -> str | None:
    return node.get(f"{{{W}}}{name}") if node is not None else None


def _number(value: str | None, default: float = 0.0) -> float:
    try:
        parsed = float(value) if value is not None else default
        return parsed if math.isfinite(parsed) and abs(parsed) <= 1_000_000_000 else default
    except (TypeError, ValueError):
        return default


def _round(value: float) -> float:
    return round(value, 3)


class _Styles:
    def __init__(self, root: etree._Element | None, theme: etree._Element | None):
        self.styles: dict[str, etree._Element] = {}
        self.default_ppr = None
        self.default_rpr = None
        self.default_paragraph_style = None
        if root is not None:
            self.default_ppr = root.find("w:docDefaults/w:pPrDefault/w:pPr", NS)
            self.default_rpr = root.find("w:docDefaults/w:rPrDefault/w:rPr", NS)
            self.styles = {
                style_id: node for node in root.findall("w:style", NS)
                if (style_id := _attr(node, "styleId"))
            }
            self.default_paragraph_style = next((key for key, node in self.styles.items()
                if _attr(node, "type") == "paragraph" and _attr(node, "default") in {"1", "true"}), None)
        self.theme_fonts: dict[str, str] = {}
        if theme is not None:
            for family in ("major", "minor"):
                family_node = theme.find(f".//a:{family}Font", NS)
                if family_node is None:
                    continue
                for script in ("latin", "ea", "cs"):
                    node = family_node.find(f"a:{script}", NS)
                    face = node.get("typeface") if node is not None else None
                    if face:
                        safe_face = "".join(char for char in face if char.isprintable())[:100]
                        if script == "latin":
                            self.theme_fonts[f"{family}Ascii"] = safe_face
                            self.theme_fonts[f"{family}HAnsi"] = safe_face
                        elif script == "ea":
                            self.theme_fonts[f"{family}EastAsia"] = safe_face
                        else:
                            self.theme_fonts[f"{family}Bidi"] = safe_face

    def _chain(self, style_id: str | None) -> list[etree._Element]:
        chain: list[etree._Element] = []
        seen: set[str] = set()
        while style_id and style_id not in seen and (style := self.styles.get(style_id)) is not None:
            seen.add(style_id)
            chain.append(style)
            style_id = _attr(style.find("w:basedOn", NS), "val")
        return chain

    def paragraph_properties(self, paragraph: etree._Element) -> list[etree._Element]:
        direct = paragraph.find("w:pPr", NS)
        style_id = _attr(direct.find("w:pStyle", NS), "val") if direct is not None else None
        values = [direct] if direct is not None else []
        values.extend(node for style in self._chain(style_id or self.default_paragraph_style) if (node := style.find("w:pPr", NS)) is not None)
        if self.default_ppr is not None:
            values.append(self.default_ppr)
        return values

    def run_properties(self, paragraph: etree._Element, run: etree._Element) -> list[etree._Element]:
        direct = run.find("w:rPr", NS)
        char_style = _attr(direct.find("w:rStyle", NS), "val") if direct is not None else None
        ppr = paragraph.find("w:pPr", NS)
        para_style = _attr(ppr.find("w:pStyle", NS), "val") if ppr is not None else None
        values = [direct] if direct is not None else []
        values.extend(node for style in self._chain(char_style) if (node := style.find("w:rPr", NS)) is not None)
        values.extend(node for style in self._chain(para_style or self.default_paragraph_style) if (node := style.find("w:rPr", NS)) is not None)
        if self.default_rpr is not None:
            values.append(self.default_rpr)
        return values

    def font(self, properties: list[etree._Element]) -> str | None:
        for rpr in properties:
            fonts = rpr.find("w:rFonts", NS)
            if fonts is None:
                continue
            for name in ("ascii", "hAnsi", "eastAsia", "cs"):
                if value := _attr(fonts, name):
                    return "".join(char for char in value if char.isprintable())[:100]
            for name in ("asciiTheme", "hAnsiTheme", "eastAsiaTheme", "csTheme"):
                if value := _attr(fonts, name):
                    return self.theme_fonts.get(value)
        return None

    @staticmethod
    def size(properties: list[etree._Element]) -> float | None:
        for rpr in properties:
            node = rpr.find("w:sz", NS)
            if node is not None and _attr(node, "val") is not None:
                return _number(_attr(node, "val")) / 2
        return None

    @staticmethod
    def property_node(properties: list[etree._Element], tag: str) -> etree._Element | None:
        for ppr in properties:
            if (node := ppr.find(f"w:{tag}", NS)) is not None:
                return node
        return None

    @staticmethod
    def property_attr(properties: list[etree._Element], tag: str, name: str) -> str | None:
        for ppr in properties:
            value = _attr(ppr.find(f"w:{tag}", NS), name)
            if value is not None:
                return value
        return None

    def bold(self, paragraph: etree._Element, run: etree._Element) -> bool:
        def enabled(node):
            return node is not None and (_attr(node, "val") or "1").lower() not in {"0", "false", "off"}
        value = enabled(self.default_rpr.find("w:b", NS)) if self.default_rpr is not None else False
        ppr, rpr = paragraph.find("w:pPr", NS), run.find("w:rPr", NS)
        pstyle = _attr(ppr.find("w:pStyle", NS), "val") if ppr is not None else None
        rstyle = _attr(rpr.find("w:rStyle", NS), "val") if rpr is not None else None
        for chain in (self._chain(pstyle or self.default_paragraph_style), self._chain(rstyle)):
            for style in reversed(chain):
                if enabled(style.find("w:rPr/w:b", NS)):
                    value = not value
        direct = rpr.find("w:b", NS) if rpr is not None else None
        return enabled(direct) if direct is not None else value


@dataclass(frozen=True)
class FirstPageScope:
    status: str
    texts: set[etree._Element]
    paragraphs: set[etree._Element]
    runs: set[etree._Element]
    sections: set[etree._Element | None]
    boundary_node: etree._Element | None = None
    images: set[etree._Element] = field(default_factory=set)


def first_page_scope(document: etree._Element, resolver: _Styles) -> FirstPageScope:
    """Locate the first page boundary without guessing a number of paragraphs.

    Word can save calculated page boundaries as lastRenderedPageBreak. Explicit
    page/section breaks and inherited pageBreakBefore are also supported. A DOCX
    without any of these cannot reliably identify page one without a layout engine.
    Original nodes and indexes are retained for finding locations and HTML preview.
    """
    body = document.find("w:body", NS)
    if body is None:
        return FirstPageScope("BOUNDARY_UNKNOWN", set(), set(), set(), set())
    nodes = list(body.iter())
    order = {node: index for index, node in enumerate(nodes)}
    paragraphs = body.findall(".//w:p", NS)
    boundaries: list[tuple[float, etree._Element]] = []
    for node in nodes:
        if node.tag == f"{{{W}}}lastRenderedPageBreak" or (
            node.tag == f"{{{W}}}br" and _attr(node, "type") == "page"
        ):
            boundaries.append((order[node] + 0.5, node))
    section_ends = [
        (paragraph, section) for paragraph in paragraphs
        if (section := paragraph.find("w:pPr/w:sectPr", NS)) is not None
    ]
    sections = [section for _, section in section_ends]
    if (final_section := body.find("w:sectPr", NS)) is not None:
        sections.append(final_section)
    for index, paragraph in enumerate(paragraphs):
        page_break = resolver.property_node(resolver.paragraph_properties(paragraph), "pageBreakBefore")
        if index and page_break is not None and (_attr(page_break, "val") or "true").lower() not in {"0", "false", "off"}:
            boundaries.append((order[paragraph] - 0.5, paragraph))
    for index, (paragraph, _) in enumerate(section_ends):
        # The following section's properties specify how that section begins.
        if index + 1 < len(sections):
            next_type = _attr(sections[index + 1].find("w:type", NS), "val") or "nextPage"
            if next_type in {"nextPage", "evenPage", "oddPage"}:
                boundaries.append((max(order[node] for node in paragraph.iter()) + 0.5, paragraph))
    if not boundaries:
        return FirstPageScope("BOUNDARY_UNKNOWN", set(), set(), set(), set())
    boundary, boundary_node = min(boundaries, key=lambda item: item[0])
    texts = {node for node in nodes if node.tag == f"{{{W}}}t" and order[node] > boundary}
    images = {node for node in nodes if node.tag in {f"{{{W}}}drawing", f"{{{W}}}pict"} and order[node] > boundary}
    included_paragraphs = {
        paragraph for paragraph in paragraphs
        if any(node in texts and (node.text or "").strip() for node in paragraph.findall(".//w:t", NS))
    }
    included_runs = {
        run for paragraph in included_paragraphs for run in paragraph.findall(".//w:r", NS)
        if any(node in texts and (node.text or "").strip() for node in run.findall(".//w:t", NS))
    }
    has_content = any((node.text or "").strip() for node in texts) or bool(images)
    included_sections = {section for section in sections if order[section] > boundary}
    # A section's sectPr is inside the last paragraph's pPr, before its runs.
    # A boundary inside that paragraph still leaves this section in scope.
    included_sections.update(
        section for paragraph, section in section_ends
        if max(order[node] for node in paragraph.iter()) > boundary
    )
    if not sections:
        included_sections.add(None)
    return FirstPageScope(
        "APPLIED" if has_content else "NO_CONTENT", texts,
        included_paragraphs, included_runs, included_sections, boundary_node, images,
    )


class DocumentAnalyzer:
    def __init__(self, *, max_findings: int):
        self.max_findings = max_findings
        self.findings: list[AnalyzerFinding] = []
        self.truncated = False
        self.paragraph_types: dict[int, str] = {}

    def _add(
        self, rule: AnalyzerRule, code: str, property_name: str, location: dict[str, Any],
        expected: dict[str, Any], actual: dict[str, Any],
    ) -> None:
        if len(self.findings) >= self.max_findings:
            self.truncated = True
            return
        if (paragraph_type := self.paragraph_types.get(location.get("paragraph_index"))) is not None:
            location = {**location, "paragraph_type": paragraph_type}
        self.findings.append(AnalyzerFinding(
            check_rule_id=rule.id, rule_type=rule.rule_type, category=rule.category,
            severity=rule.severity, code=code, property_name=property_name,
            location=location, expected=expected, actual=actual,
        ))

    def analyze(self, source: str | Path | BinaryIO, rules: list[AnalyzerRule], paragraph_overrides=None) -> tuple[list[AnalyzerFinding], dict[str, Any]]:
        from app.services.document_paragraphs import classify_paragraphs
        self.findings = []
        self.truncated = False
        with zipfile.ZipFile(source) as package:
            document = _xml(package.read("word/document.xml"))
            styles = _xml(package.read("word/styles.xml")) if "word/styles.xml" in package.namelist() else None
            theme = _xml(package.read("word/theme/theme1.xml")) if "word/theme/theme1.xml" in package.namelist() else None
        resolver = _Styles(styles, theme)
        scope = first_page_scope(document, resolver)
        self.paragraph_types = {item["paragraph_index"]: item["paragraph_type"]
                                for item in classify_paragraphs(document, resolver, paragraph_overrides)}
        heading_types = {f"HEADING_{level['level']}" for rule in rules if rule.rule_type == CheckRuleType.HEADINGS
                         for level in rule.config["levels"]}
        body_scope = self._type_scope(document, scope, set(self.paragraph_types.values()) - heading_types)
        evaluated = 0
        skipped = 0
        for rule in rules:
            if scope.status != "APPLIED" or rule.rule_type not in SUPPORTED_RULE_TYPES:
                skipped += 1
                continue
            evaluated += 1
            if rule.rule_type == CheckRuleType.PAGE_FORMAT_MARGINS:
                self._page(rule, document, scope)
            elif rule.rule_type == CheckRuleType.FONTS_SIZES:
                self._fonts(rule, document, resolver, body_scope)
            elif rule.rule_type == CheckRuleType.PARAGRAPH_SPACING_INDENTS:
                self._paragraphs(rule, document, resolver, body_scope)
            elif rule.rule_type == CheckRuleType.HEADINGS:
                self._headings(rule, document, resolver, scope)
        summary = {
            "analyzer_version": ANALYZER_VERSION,
            "rules_total": len(rules), "rules_evaluated": evaluated, "rules_skipped": skipped,
            "findings_count": len(self.findings), "findings_truncated": self.truncated,
            "first_page_exclusion": scope.status,
        }
        return self.findings, summary

    def _type_scope(self, document, scope, kinds):
        paragraphs = {p for index, p in enumerate(document.findall(".//w:p", NS), 1)
                      if self.paragraph_types[index] in kinds and p in scope.paragraphs}
        runs = {run for p in paragraphs for run in p.findall(".//w:r", NS) if run in scope.runs}
        return replace(scope, paragraphs=paragraphs, runs=runs)

    def _headings(self, rule, document, resolver, scope):
        from app.services.document_paragraphs import NUMBERED, CHAPTER, SECTION_NAMES
        for level in rule.config["levels"]:
            selected = self._type_scope(document, scope, {f"HEADING_{level['level']}"})
            level_rule = replace(rule, config=level)
            self._fonts(level_rule, document, resolver, selected)
            self._paragraphs(level_rule, document, resolver, selected)
            for index, paragraph in enumerate(document.findall(".//w:p", NS), 1):
                if paragraph not in selected.paragraphs:
                    continue
                if rule.config.get("require_numbering"):
                    text = " ".join("".join(node.text or "" for node in paragraph.findall(".//w:t", NS)
                                            if node in scope.texts).split())
                    num = resolver.property_node(resolver.paragraph_properties(paragraph), "numPr")
                    has_num = num is not None and _attr(num.find("w:numId", NS), "val") not in {None, "0"}
                    if not (has_num or NUMBERED.match(text) or CHAPTER.match(text)
                            or text.casefold().strip(" .:") in SECTION_NAMES):
                        self._add(rule, "HEADING_NUMBERING_MISSING", "numbering",
                                  {"part": "word/document.xml", "paragraph_index": index},
                                  {"value": True}, {"value": False})
                if level.get("bold") is not None:
                    for run_index, run in enumerate(paragraph.findall(".//w:r", NS), 1):
                        if run not in selected.runs:
                            continue
                        actual = resolver.bold(paragraph, run)
                        if actual != level["bold"]:
                            self._add(rule, "HEADING_BOLD_MISMATCH", "bold",
                                      {"part": "word/document.xml", "paragraph_index": index, "run_index": run_index},
                                      {"value": level["bold"]}, {"value": actual})

    def _page(self, rule: AnalyzerRule, document: etree._Element, scope: FirstPageScope) -> None:
        sections = document.findall(".//w:sectPr", NS)
        for index, section in enumerate(sections or [None], 1):
            if section not in scope.sections:
                continue
            location = {"part": "word/document.xml", "section_index": index}
            size = section.find("w:pgSz", NS) if section is not None else None
            width = _number(_attr(size, "w")) / 1440 * 25.4 if size is not None else 0
            height = _number(_attr(size, "h")) / 1440 * 25.4 if size is not None else 0
            actual_orientation = (_attr(size, "orient") or "portrait").upper() if size is not None else "UNKNOWN"
            expected_orientation = rule.config["orientation"]
            if actual_orientation != expected_orientation:
                self._add(rule, "PAGE_ORIENTATION_MISMATCH", "orientation", location,
                          {"value": expected_orientation}, {"value": actual_orientation})
            expected_size = ((rule.config.get("width_mm"), rule.config.get("height_mm"))
                             if rule.config["page_size"] == "CUSTOM" else PAGE_SIZES_MM[rule.config["page_size"]])
            if expected_orientation == "LANDSCAPE":
                expected_size = (expected_size[1], expected_size[0])
            if abs(width - expected_size[0]) > 0.6 or abs(height - expected_size[1]) > 0.6:
                self._add(rule, "PAGE_SIZE_MISMATCH", "page_size", location,
                          {"width_mm": expected_size[0], "height_mm": expected_size[1], "name": rule.config["page_size"]},
                          {"width_mm": _round(width), "height_mm": _round(height)})
            margins = section.find("w:pgMar", NS) if section is not None else None
            for side in ("top", "right", "bottom", "left"):
                actual = _number(_attr(margins, side)) / 1440 * 25.4 if margins is not None else 0
                expected = rule.config["margins"][f"{side}_mm"]
                if abs(actual - expected) > 0.3:
                    self._add(rule, "PAGE_MARGIN_MISMATCH", f"margin_{side}", location,
                              {"value": expected, "unit": "mm"}, {"value": _round(actual), "unit": "mm"})

    def _fonts(self, rule: AnalyzerRule, document: etree._Element, resolver: _Styles, scope: FirstPageScope) -> None:
        allowed = {font.casefold(): font for font in (rule.config.get("allowed_fonts") or [])}
        for paragraph_index, paragraph in enumerate(document.findall(".//w:p", NS), 1):
            for run_index, run in enumerate(paragraph.findall(".//w:r", NS), 1):
                if run not in scope.runs:
                    continue
                properties = resolver.run_properties(paragraph, run)
                location = {"part": "word/document.xml", "paragraph_index": paragraph_index, "run_index": run_index}
                font = resolver.font(properties)
                if allowed and (font is None or font.casefold() not in allowed):
                    self._add(rule, "FONT_NOT_ALLOWED", "font", location,
                              {"allowed": list(rule.config["allowed_fonts"])}, {"value": font})
                size = resolver.size(properties)
                if size is None or size < rule.config["min_size_pt"] or size > rule.config["max_size_pt"]:
                    self._add(rule, "FONT_SIZE_OUT_OF_RANGE", "font_size", location,
                              {"min": rule.config["min_size_pt"], "max": rule.config["max_size_pt"], "unit": "pt"},
                              {"value": _round(size) if size is not None else None, "unit": "pt"})

    def _paragraphs(self, rule: AnalyzerRule, document: etree._Element, resolver: _Styles, scope: FirstPageScope) -> None:
        for index, paragraph in enumerate(document.findall(".//w:p", NS), 1):
            if paragraph not in scope.paragraphs:
                continue
            properties = resolver.paragraph_properties(paragraph)
            location = {"part": "word/document.xml", "paragraph_index": index}
            def attr(tag, name):
                return resolver.property_attr(properties, tag, name)
            alignment = attr("jc", "val") or "left"
            actual_alignment = {"left": "LEFT", "start": "LEFT", "center": "CENTER", "right": "RIGHT",
                                "end": "RIGHT", "both": "JUSTIFY", "distribute": "JUSTIFY"}.get(alignment, "UNKNOWN")
            if rule.config.get("alignment") is not None and actual_alignment != rule.config["alignment"]:
                self._add(rule, "PARAGRAPH_ALIGNMENT_MISMATCH", "alignment", location,
                          {"value": rule.config["alignment"]}, {"value": actual_alignment})
            values: dict[str, tuple[float, str]] = {
                "space_before": (_number(attr("spacing", "before")) / 20, "pt"),
                "space_after": (_number(attr("spacing", "after")) / 20, "pt"),
            }
            line_rule = attr("spacing", "lineRule") or "auto"
            line_raw = _number(attr("spacing", "line"), 240)
            actual_line = line_raw / (240 if line_rule == "auto" else 20)
            if rule.config.get("line_spacing") is not None and (line_rule != "auto" or abs(actual_line - rule.config["line_spacing"]) > 0.01):
                self._add(rule, "PARAGRAPH_SPACING_MISMATCH", "line_spacing", location,
                          {"value": rule.config["line_spacing"], "unit": "multiple", "mode": "auto"},
                          {"value": _round(actual_line), "unit": "multiple" if line_rule == "auto" else "pt", "mode": line_rule})
            left = attr("ind", "left") or attr("ind", "start")
            right = attr("ind", "right") or attr("ind", "end")
            # firstLine/hanging are mutually exclusive at each inheritance level.
            first = 0.0
            for ppr in properties:
                indent = ppr.find("w:ind", NS)
                if _attr(indent, "hanging") is not None or _attr(indent, "firstLine") is not None:
                    first = -_number(_attr(indent, "hanging")) if _attr(indent, "hanging") is not None else _number(_attr(indent, "firstLine"))
                    break
            values.update({
                "first_line_indent": (first / 1440 * 25.4, "mm"),
                "left_indent": (_number(left) / 1440 * 25.4, "mm"),
                "right_indent": (_number(right) / 1440 * 25.4, "mm"),
            })
            expected_names = {
                "space_before": "space_before_pt", "space_after": "space_after_pt",
                "first_line_indent": "first_line_indent_mm", "left_indent": "left_indent_mm",
                "right_indent": "right_indent_mm",
            }
            for property_name, (actual, unit) in values.items():
                expected = rule.config.get(expected_names[property_name])
                if expected is None:
                    continue
                tolerance = 0.1 if unit == "pt" else 0.2
                if abs(actual - expected) > tolerance:
                    code = "PARAGRAPH_SPACING_MISMATCH" if property_name.startswith("space_") else "PARAGRAPH_INDENT_MISMATCH"
                    self._add(rule, code, property_name, location,
                              {"value": expected, "unit": unit}, {"value": _round(actual), "unit": unit})


def analyze_document(source: str | Path | BinaryIO, rules: list[AnalyzerRule], *, max_findings: int, paragraph_overrides=None):
    return DocumentAnalyzer(max_findings=max_findings).analyze(source, rules, paragraph_overrides)
