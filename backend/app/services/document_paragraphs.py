"""Deterministic paragraph classification using source OOXML, never target rules."""
from __future__ import annotations

import re
from collections import Counter
from typing import BinaryIO
from pathlib import Path
import zipfile

from app.services.document_analyzer import NS, _Styles, _attr, _xml, first_page_scope

SECTION_NAMES = {
    "введение", "заключение", "содержание", "оглавление", "список литературы",
    "список использованных источников", "список использованной литературы", "приложения",
    "кіріспе", "қорытынды", "мазмұны", "пайдаланылған әдебиеттер", "әдебиеттер тізімі",
    "пайдаланылған әдебиеттер тізімі", "қосымшалар",
    "introduction", "conclusion", "conclusions", "contents", "table of contents",
    "references", "bibliography", "appendices", "abstract",
}
CAPTION = re.compile(r"^(?:(?:рисунок|рис\.?|таблица|табл\.?|figure|fig\.?|table|сурет|кесте)\s*[\dIVX]|\d+(?:[.\-]\d+)*\s*[-–—]?\s*(?:сурет|кесте)\b)", re.I)
NUMBERED = re.compile(r"^(\d{1,3}(?:\.\d{1,3}){0,5})([.)]?)\s+(.+)$")
CHAPTER = re.compile(r"^(?:глава|раздел|chapter|тарау|бөлім)\s+[\dIVX]+\b|^\d+\s*[-–—]?\s*(?:тарау|бөлім)\b", re.I)


def paragraph_structure(paragraph, resolver):
    properties = resolver.paragraph_properties(paragraph)
    outline = resolver.property_node(properties, "outlineLvl")
    if outline is not None:
        value = _attr(outline, "val")
        if value is not None and value.isdigit():
            level = int(value)
            # Word 9 explicitly marks body text, overriding a heading ancestor.
            return (f"HEADING_{level + 1}" if level < 6 else "BODY"), "STRUCTURE"
    ppr = paragraph.find("w:pPr", NS)
    style_id = _attr(ppr.find("w:pStyle", NS), "val") if ppr is not None else None
    for style in resolver._chain(style_id or resolver.default_paragraph_style):
        for value in (_attr(style, "styleId"), _attr(style.find("w:name", NS), "val")):
            match = re.fullmatch(r"(?:heading|заголовок|тақырып)\s*([1-6])", value or "", re.I)
            if match:
                return f"HEADING_{match[1]}", "STRUCTURE"
    return None


def classify_paragraphs(document, resolver, overrides=None):
    overrides = overrides or {}
    scope = first_page_scope(document, resolver)
    paragraphs = document.findall(".//w:p", NS)
    records = []
    sizes = Counter()
    for paragraph in paragraphs:
        text = " ".join("".join(node.text or "" for node in paragraph.findall(".//w:t", NS)
                                if node in scope.texts).split())
        runs = [run for run in paragraph.findall(".//w:r", NS) if run in scope.runs]
        formats = [(resolver.size(resolver.run_properties(paragraph, run)), resolver.bold(paragraph, run),
                    sum(len(node.text or "") for node in run.findall(".//w:t", NS) if node in scope.texts))
                   for run in runs]
        structural = paragraph_structure(paragraph, resolver)
        if not structural or structural[0] == "BODY":
            for size, _, count in formats:
                if size:
                    sizes[size] += count
        records.append((paragraph, text, formats, structural))
    body_size = sizes.most_common(1)[0][0] if sizes else 14
    output = []
    for index, (paragraph, text, formats, structural) in enumerate(records, 1):
        kind, source = structural or ("BODY", "BODY")
        if structural is None and text and len(text) <= 160 and len(text.split()) <= 18:
            props = resolver.paragraph_properties(paragraph)
            ppr = paragraph.find("w:pPr", NS)
            style_id = _attr(ppr.find("w:pStyle", NS), "val") if ppr is not None else ""
            chain_names = " ".join((_attr(s, "styleId") or "") + " " + (_attr(s.find("w:name", NS), "val") or "")
                                   for s in resolver._chain(style_id))
            excluded_style = re.search(r"caption|подпись|toc\s*\d|оглавление", chain_names, re.I)
            in_table = bool(paragraph.xpath("ancestor::w:tc", namespaces=NS))
            listing = resolver.property_node(props, "numPr")
            numbered = NUMBERED.match(text)
            characters = sum(count for _, _, count in formats) or 1
            bold = sum(count for _, bold, count in formats if bold) / characters >= 0.8
            larger = sum(count for size, _, count in formats if size and size > body_size + 0.5) / characters >= 0.8
            keep = resolver.property_node(props, "keepNext")
            kept = keep is not None and (_attr(keep, "val") or "1") not in {"0", "false", "off"}
            centered = resolver.property_attr(props, "jc", "val") == "center"
            # Alignment only adds evidence; it never vetoes other heading signals.
            emphasis = bold or larger or kept or (text.isupper() and len(text) > 4)
            if not excluded_style and not in_table and not CAPTION.match(text):
                normalized = text.casefold().strip(" .:\t")
                if normalized in SECTION_NAMES and listing is None:
                    kind, source = "HEADING_1", "HEURISTIC"
                elif CHAPTER.match(text) and not text.endswith((".", ";", ":", "?", "!")):
                    kind, source = "HEADING_1", "HEURISTIC"
                elif numbered and not text.endswith((".", ";", ":", "?", "!")):
                    level = numbered[1].count(".") + 1
                    # Bare "1. item" / automatic numbered lists need multiple
                    # heading signals; ordinary short list items stay body text.
                    list_like = listing is not None or numbered[2] in {".", ")"}
                    if (not list_like and (level > 1 or emphasis)) or (list_like and bold and (larger or kept)):
                        kind, source = f"HEADING_{min(level, 6)}", "HEURISTIC"
                elif listing is not None and bold and (larger or kept) and not text.endswith((".", ";", ":", "?", "!")):
                    # Word-generated numbering is not part of w:t. Require two
                    # additional signals to avoid promoting ordinary list items.
                    level = _attr(listing.find("w:ilvl", NS), "val") or "0"
                    if level.isdigit() and int(level) < 6 and _attr(listing.find("w:numId", NS), "val") not in {None, "0"}:
                        kind, source = f"HEADING_{int(level) + 1}", "HEURISTIC"
                elif (listing is None and len(text.split()) <= 12
                      and ((bold and larger) or (centered and kept and (bold or larger)))
                      and not text.endswith((".", ";", ":", "?", "!"))):
                    # Short custom titles need multiple signals. Centering alone,
                    # or with bold alone, cannot promote an ordinary paragraph.
                    kind, source = "HEADING_1", "HEURISTIC"
        automatic = kind
        if (manual := overrides.get(str(index))) is not None:
            kind, source = manual, "MANUAL"
        output.append({"paragraph_index": index, "automatic_type": automatic,
                       "paragraph_type": kind, "source": source,
                       "excluded": paragraph not in scope.paragraphs})
    return output


def inspect_paragraphs(source: str | Path | BinaryIO, overrides=None):
    with zipfile.ZipFile(source) as package:
        document = _xml(package.read("word/document.xml"))
        styles = _xml(package.read("word/styles.xml")) if "word/styles.xml" in package.namelist() else None
        theme = _xml(package.read("word/theme/theme1.xml")) if "word/theme/theme1.xml" in package.namelist() else None
    return classify_paragraphs(document, _Styles(styles, theme), overrides)
