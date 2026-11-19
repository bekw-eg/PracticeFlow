"""Safe, read-only DOCX to HTML preview for teacher document checks.

Only HTML elements and inline styles produced by this module are returned.
Document text is escaped and relationships, embedded HTML, macros, links and
scripts are never copied into the preview.
"""
from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import BinaryIO

from lxml import etree

from app.services.document_analyzer import FirstPageScope, NS, W, _Styles, _attr, _number, _xml, first_page_scope
from app.services.docx_preview_assets import embedded_images, numbering_labels


@dataclass(frozen=True)
class DocxHtmlPreview:
    html: str
    paragraph_count: int
    page_width_mm: float
    page_height_mm: float
    margin_top_mm: float
    margin_right_mm: float
    margin_bottom_mm: float
    margin_left_mm: float


def _safe_font(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"[^\w \-]", "", value, flags=re.UNICODE).strip()
    return cleaned[:100] or None


DEFAULT_TAB_STOP_MM = 12.7
_TAB_ALIGNMENTS = {
    "left": "left", "start": "left", "num": "left",
    "right": "right", "end": "right", "center": "center", "decimal": "decimal",
}
_TAB_LEADERS = {"dot", "hyphen", "underscore", "heavy", "middleDot"}
_MAX_TAB_POSITION_TWIPS = 34_020  # 600 mm, far beyond any supported page width.


def _twips_to_mm(value: float) -> float:
    return value / 1440 * 25.4


def _tab_stops(properties: list[etree._Element], left_mm: float, hanging_mm: float) -> list[tuple[float, str, str]]:
    """Merge Word tab stops from defaults, styles and direct formatting.

    Stops are cumulative through the style chain; ``w:val="clear"`` removes an
    inherited stop at the same position. A hanging indent adds Word's implicit
    stop at the left indent so ``1.1<tab>Title`` lines up like in Word.
    """
    stops: dict[int, tuple[str, str]] = {}
    for paragraph_properties in reversed(properties):
        tabs = paragraph_properties.find("w:tabs", NS)
        if tabs is None:
            continue
        for tab in tabs.findall("w:tab", NS):
            position = round(_number(_attr(tab, "pos"), -1))
            kind = _attr(tab, "val")
            if kind == "clear":
                stops.pop(position, None)
            elif kind in _TAB_ALIGNMENTS and 0 <= position <= _MAX_TAB_POSITION_TWIPS:
                leader = _attr(tab, "leader")
                stops[position] = (_TAB_ALIGNMENTS[kind], leader if leader in _TAB_LEADERS else "none")
    result = [(round(_twips_to_mm(position), 2), alignment, leader)
              for position, (alignment, leader) in sorted(stops.items())]
    if hanging_mm > 0 and 0 < left_mm <= 100 and all(abs(position - left_mm) > 0.01 for position, _, _ in result):
        result.append((round(left_mm, 2), "left", "none"))
        result.sort()
    return result[:64]


def _default_tab_stop_mm(settings: etree._Element | None) -> float:
    value = _number(_attr(settings.find("w:defaultTabStop", NS) if settings is not None else None, "val"), 720)
    millimetres = _twips_to_mm(value)
    return round(millimetres, 2) if 1 <= millimetres <= 100 else DEFAULT_TAB_STOP_MM


def _first_node(properties: list[etree._Element], tag: str) -> etree._Element | None:
    for properties_node in properties:
        if (node := properties_node.find(f"w:{tag}", NS)) is not None:
            return node
    return None


def _toggle(properties: list[etree._Element], tag: str) -> bool:
    node = _first_node(properties, tag)
    if node is None:
        return False
    return (_attr(node, "val") or "true").lower() not in {"0", "false", "off", "none"}


def _run_html(paragraph: etree._Element, run: etree._Element, run_index: int, styles: _Styles, scope: FirstPageScope, images) -> str:
    parts: list[str] = []
    for node in run.iter():
        if node in images:
            parts.append(images[node])
            continue
        if any(parent in images for parent in node.iterancestors()):
            continue
        if node.tag == f"{{{W}}}t":
            excluded = ' data-check-excluded="true"' if node not in scope.texts else ""
            parts.append(f'<span data-check-text="true"{excluded}>{escape(node.text or "")}</span>')
        elif node.tag == f"{{{W}}}lastRenderedPageBreak" and node is scope.boundary_node:
            parts.append('<br data-page-break="true">')
        elif node.tag == f"{{{W}}}tab":
            # The browser paginator sizes this to the paragraph's Word tab stop.
            parts.append('<span class="pf-tab">\t</span>')
        elif node.tag == f"{{{W}}}ptab":
            alignment = _attr(node, "alignment")
            leader = _attr(node, "leader")
            attributes = f' data-ptab="{alignment}"' if alignment in {"left", "center", "right"} else ""
            if leader in _TAB_LEADERS:
                attributes += f' data-ptab-leader="{leader}"'
            parts.append(f'<span class="pf-tab"{attributes}>\t</span>')
        elif node.tag in {f"{{{W}}}br", f"{{{W}}}cr"}:
            parts.append('<br data-page-break="true">' if _attr(node, "type") == "page" else "<br>")
        elif node.tag == f"{{{W}}}noBreakHyphen":
            parts.append("&#8209;")
        elif node.tag == f"{{{W}}}softHyphen":
            parts.append("&shy;")
    if not parts:
        return ""

    properties = styles.run_properties(paragraph, run)
    css: list[str] = []
    if font := _safe_font(styles.font(properties)):
        css.append(f"font-family:'{font}',serif")
    if (size := styles.size(properties)) is not None and 1 <= size <= 200:
        css.append(f"font-size:{round(size, 2)}pt")
    if styles.bold(paragraph, run):
        css.append("font-weight:700")
    if _toggle(properties, "i"):
        css.append("font-style:italic")
    decorations: list[str] = []
    underline = _first_node(properties, "u")
    if underline is not None and (_attr(underline, "val") or "single") != "none":
        decorations.append("underline")
    if _toggle(properties, "strike"):
        decorations.append("line-through")
    if decorations:
        css.append(f"text-decoration:{' '.join(decorations)}")
    color = _attr(_first_node(properties, "color"), "val")
    if color and re.fullmatch(r"[0-9A-Fa-f]{6}", color):
        css.append(f"color:#{color}")
    style = f' style="{escape(";".join(css), quote=True)}"' if css else ""
    return f'<span data-run-index="{run_index}"{style}>{"".join(parts)}</span>'


def _paragraph_html(paragraph: etree._Element, index: int, styles: _Styles, scope: FirstPageScope, images, labels) -> str:
    properties = styles.paragraph_properties(paragraph)
    css: list[str] = []
    alignment = _attr(styles.property_node(properties, "jc"), "val")
    alignment_map = {"left": "left", "start": "left", "center": "center", "right": "right", "end": "right", "both": "justify", "distribute": "justify"}
    if alignment in alignment_map:
        css.append(f"text-align:{alignment_map[alignment]}")

    def attr(tag, name):
        return styles.property_attr(properties, tag, name)
    before = _number(attr("spacing", "before")) / 20
    after = _number(attr("spacing", "after")) / 20
    if 0 <= before <= 200:
        css.append(f"margin-top:{round(before, 2)}pt")
    if 0 <= after <= 200:
        css.append(f"margin-bottom:{round(after, 2)}pt")
    line_rule = attr("spacing", "lineRule") or "auto"
    line_raw = _number(attr("spacing", "line"), 240)
    if line_rule == "auto" and 0 < line_raw <= 2400:
        css.append(f"line-height:{round(line_raw / 240, 3)}")
    elif line_rule in {"exact", "atLeast"} and 0 < line_raw <= 4000:
        css.append(f"line-height:{round(line_raw / 20, 3)}pt")

    left = _number(attr("ind", "left") or attr("ind", "start")) / 1440 * 25.4
    right = _number(attr("ind", "right") or attr("ind", "end")) / 1440 * 25.4
    first, hanging = 0.0, 0.0
    for ppr in properties:
        indent = ppr.find("w:ind", NS)
        if _attr(indent, "firstLine") is not None or _attr(indent, "hanging") is not None:
            first = _number(_attr(indent, "firstLine")) / 1440 * 25.4
            hanging = _number(_attr(indent, "hanging")) / 1440 * 25.4
            break
    if 0 < left <= 100:
        css.append(f"margin-left:{round(left, 2)}mm")
    if 0 < right <= 100:
        css.append(f"margin-right:{round(right, 2)}mm")
    if first:
        css.append(f"text-indent:{round(first, 2)}mm")
    elif hanging:
        css.append(f"text-indent:-{round(hanging, 2)}mm")

    runs = [
        _run_html(paragraph, run, run_index, styles, scope, images)
        for run_index, run in enumerate(paragraph.findall(".//w:r", NS), 1)
    ]
    content = "".join(runs)
    if paragraph in labels:
        content = f'<span class="pf-docx-list-marker">{escape(labels[paragraph])}</span>{content}'
    style = f' style="{escape(";".join(css), quote=True)}"' if css else ""
    page_break = ' data-page-break-before="true"' if _toggle(properties, "pageBreakBefore") else ""
    tabs = ""
    if 'class="pf-tab"' in content and (stops := _tab_stops(properties, left, hanging)):
        serialized = ";".join(f"{position:g} {alignment} {leader}" for position, alignment, leader in stops)
        tabs = f' data-tab-stops="{serialized}"'
    return f'<p data-paragraph-index="{index}"{page_break}{tabs}{style}>{content or "&nbsp;"}</p>'


_BORDER_SIDES = ("top", "left", "bottom", "right", "insideH", "insideV")
_BORDER_ALIASES = {"start": "left", "end": "right"}
_BORDER_STYLES = {
    "single": "solid", "thick": "solid", "double": "double", "dotted": "dotted",
    "dashed": "dashed", "dashSmallGap": "dashed", "dotDash": "dashed", "dotDotDash": "dashed",
}


def _border_css(node: etree._Element) -> str:
    kind = _attr(node, "val") or "none"
    if kind in {"none", "nil"}:
        return "none"
    width = max(0.25, min(6.0, _number(_attr(node, "sz"), 4) / 8))
    style = _BORDER_STYLES.get(kind, "solid")
    if style == "double":
        width = max(width * 3, 1.5)
    color = _attr(node, "color")
    color = f"#{color}" if color and re.fullmatch(r"[0-9A-Fa-f]{6}", color) else "#000000"
    return f"{round(width, 2)}pt {style} {color}"


def _collect_borders(container: etree._Element | None, borders: dict[str, str]) -> None:
    if container is None:
        return
    for node in container:
        side = etree.QName(node).localname
        side = _BORDER_ALIASES.get(side, side)
        if side in _BORDER_SIDES:
            borders[side] = _border_css(node)


def _table_borders(table: etree._Element, styles: _Styles) -> dict[str, str]:
    """Word draws no table borders unless direct formatting or a table style asks for them."""
    style_id = _attr(table.find("w:tblPr/w:tblStyle", NS), "val")
    if style_id is None:
        style_id = next((key for key, node in styles.styles.items()
                         if _attr(node, "type") == "table" and _attr(node, "default") in {"1", "true"}), None)
    borders = dict.fromkeys(_BORDER_SIDES, "none")
    for style in reversed(styles._chain(style_id)):
        _collect_borders(style.find("w:tblPr/w:tblBorders", NS), borders)
    _collect_borders(table.find("w:tblPr/w:tblBorders", NS), borders)
    return borders


def _cell_border_css(table_borders: dict[str, str], cell: dict, row: int, rows: int, columns: int) -> str:
    edges = {
        "top": table_borders["top"] if row == 0 else table_borders["insideH"],
        "bottom": table_borders["bottom"] if row + cell["rows"] >= rows else table_borders["insideH"],
        "left": table_borders["left"] if cell["column"] == 0 else table_borders["insideV"],
        "right": table_borders["right"] if cell["column"] + cell["span"] >= columns else table_borders["insideV"],
    }
    if cell["borders"] is not None:
        own: dict[str, str] = {}
        _collect_borders(cell["borders"], own)
        edges.update({side: value for side, value in own.items() if side in edges})
    return ";".join(f"border-{side}:{value}" for side, value in edges.items())


def _table_html(table, paragraph_indexes, styles, scope, images, labels) -> str:
    rows, previous = [], {}
    table_borders = _table_borders(table, styles)
    def content(parent):
        parts = []
        for child in parent:
            if child.tag == f"{{{W}}}p":
                parts.append(_paragraph_html(child, paragraph_indexes[child], styles, scope, images, labels))
            elif child.tag == f"{{{W}}}tbl":
                parts.append(_table_html(child, paragraph_indexes, styles, scope, images, labels))
            elif child.tag in {f"{{{W}}}sdt", f"{{{W}}}sdtContent"}:
                parts.append(content(child))
        return "".join(parts)
    for row in table.findall("w:tr", NS):
        cells, current = [], {}
        column = max(0, min(100, int(_number(_attr(row.find("w:trPr/w:gridBefore", NS), "val")))))
        if column:
            cells.append({"span": column, "rows": 1, "html": "", "tag": "td", "css": "", "column": 0,
                          "borders": None, "filler": True})
        header = row.find("w:trPr/w:tblHeader", NS)
        tag = "th" if header is not None and (_attr(header, "val") or "1") not in {"0", "false", "off"} else "td"
        for cell in row.findall("w:tc", NS):
            span = max(1, min(100, int(_number(_attr(cell.find("w:tcPr/w:gridSpan", NS), "val"), 1))))
            merge = cell.find("w:tcPr/w:vMerge", NS)
            key = (column, span)
            html = content(cell)
            if merge is not None and _attr(merge, "val") != "restart" and key in previous:
                origin = previous[key]
                origin["rows"] += 1
                origin["html"] += html  # Preserve every original paragraph index.
                current[key] = origin
            else:
                css = []
                alignment = _attr(cell.find("w:tcPr/w:vAlign", NS), "val")
                if alignment in {"top", "center", "bottom"}:
                    css.append("vertical-align:" + ("middle" if alignment == "center" else alignment))
                fill = _attr(cell.find("w:tcPr/w:shd", NS), "fill")
                if fill and re.fullmatch(r"[0-9A-Fa-f]{6}", fill):
                    css.append("background-color:#" + fill)
                item = {"span": span, "rows": 1, "html": html, "tag": tag, "css": ";".join(css), "column": column,
                        "borders": cell.find("w:tcPr/w:tcBorders", NS), "filler": False}
                cells.append(item)
                if merge is not None:
                    current[key] = item
            column += span
        rows.append(cells)
        previous = current
    grid_columns = sum(1 for _ in table.findall("w:tblGrid/w:gridCol", NS))
    total_columns = max([grid_columns, *(cell["column"] + cell["span"] for cells in rows for cell in cells)])
    rendered = []
    for row_index, cells in enumerate(rows):
        parts = []
        for cell in cells:
            borders = ("border:none" if cell["filler"]
                       else _cell_border_css(table_borders, cell, row_index, len(rows), total_columns))
            css = ";".join(filter(None, (cell["css"], borders)))
            parts.append(f'<{cell["tag"]} colspan="{cell["span"]}" rowspan="{cell["rows"]}" style="{css}">'
                         f'{cell["html"]}</{cell["tag"]}>')
        rendered.append('<tr>' + ''.join(parts) + '</tr>')
    columns = ''.join(f'<col style="width:{max(1, min(500, _number(_attr(col, "w")) / 1440 * 25.4)):.2f}mm">'
                      for col in table.findall("w:tblGrid/w:gridCol", NS))
    width = table.find("w:tblPr/w:tblW", NS)
    css = ""
    if _attr(width, "type") == "dxa":
        css = f'width:{max(1, min(500, _number(_attr(width, "w")) / 1440 * 25.4)):.2f}mm;max-width:100%'
    elif _attr(width, "type") == "pct":
        css = f'width:{max(1, min(100, _number(_attr(width, "w")) / 50)):.2f}%'
    alignment = _attr(table.find("w:tblPr/w:jc", NS), "val")
    if alignment == "center":
        css += ";margin-left:auto;margin-right:auto"
    elif alignment == "right":
        css += ";margin-left:auto;margin-right:0"
    return f'<table style="{css}"><colgroup>{columns}</colgroup><tbody>{"".join(rendered)}</tbody></table>'


def _page_settings(section: etree._Element | None) -> tuple[float, float, float, float, float, float]:
    size = section.find("w:pgSz", NS) if section is not None else None
    margins = section.find("w:pgMar", NS) if section is not None else None
    width = _number(_attr(size, "w"), 11906) / 1440 * 25.4
    height = _number(_attr(size, "h"), 16838) / 1440 * 25.4

    def margin(name: str, default_twips: float) -> float:
        return max(0.0, min(100.0, _number(_attr(margins, name), default_twips) / 1440 * 25.4))

    width = max(100.0, min(500.0, width))
    height = max(100.0, min(500.0, height))
    return (
        round(width, 2), round(height, 2),
        round(margin("top", 1440), 2), round(margin("right", 1440), 2),
        round(margin("bottom", 1440), 2), round(margin("left", 1440), 2),
    )


def render_docx_html(source: str | Path | BinaryIO) -> DocxHtmlPreview:
    with zipfile.ZipFile(source) as package:
        document = _xml(package.read("word/document.xml"))
        styles_root = _xml(package.read("word/styles.xml")) if "word/styles.xml" in package.namelist() else None
        theme = _xml(package.read("word/theme/theme1.xml")) if "word/theme/theme1.xml" in package.namelist() else None
        settings = _xml(package.read("word/settings.xml")) if "word/settings.xml" in package.namelist() else None
        default_tab = _default_tab_stop_mm(settings)
        styles = _Styles(styles_root, theme)
        scope = first_page_scope(document, styles)
        images = embedded_images(package, document, scope)
        labels = numbering_labels(package, document, styles)
    paragraphs = document.findall(".//w:p", NS)
    paragraph_indexes = {paragraph: index for index, paragraph in enumerate(paragraphs, 1)}
    body = document.find("w:body", NS)
    # Section properties at the end of a section describe the preceding blocks.
    # Use the analyzer's section numbering for finding locations.
    section_nodes = document.findall(".//w:sectPr", NS)
    section_indexes = {node: index for index, node in enumerate(section_nodes, 1)}
    sections: list[str] = []
    blocks: list[str] = []
    first_settings = None

    def flush_section(section: etree._Element | None) -> None:
        nonlocal first_settings
        settings = _page_settings(section)
        if first_settings is None:
            first_settings = settings
        attributes = " ".join(
            f'data-{key}="{value}"' for key, value in zip(
                ("page-width", "page-height", "margin-top", "margin-right", "margin-bottom", "margin-left"),
                settings,
            )
        )
        index = section_indexes.get(section, len(sections) + 1)
        sections.append(
            f'<section class="pf-docx-content" data-section-index="{index}" {attributes} '
            f'data-default-tab="{default_tab:g}">{"".join(blocks)}</section>'
        )
        blocks.clear()

    def visit(parent: etree._Element) -> None:
        for child in parent:
            if child.tag == f"{{{W}}}p":
                blocks.append(_paragraph_html(child, paragraph_indexes[child], styles, scope, images, labels))
                if (section := child.find("w:pPr/w:sectPr", NS)) is not None:
                    flush_section(section)
            elif child.tag == f"{{{W}}}tbl":
                blocks.append(_table_html(child, paragraph_indexes, styles, scope, images, labels))
            elif child.tag == f"{{{W}}}sectPr":
                flush_section(child)
            elif child.tag not in {f"{{{W}}}sdtPr", f"{{{W}}}sdtEndPr"}:
                visit(child)

    if body is not None:
        visit(body)
    if blocks or not sections:
        flush_section(None)
    width, height, top, right, bottom, left = first_settings
    return DocxHtmlPreview(
        html="".join(sections),
        paragraph_count=len(paragraphs),
        page_width_mm=width,
        page_height_mm=height,
        margin_top_mm=top,
        margin_right_mm=right,
        margin_bottom_mm=bottom,
        margin_left_mm=left,
    )
