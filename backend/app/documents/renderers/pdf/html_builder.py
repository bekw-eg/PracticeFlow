"""Converts our DocumentModel into print-ready HTML for WeasyPrint (rule
29/30). This is a THIRD renderer walking the same structured document tree
as the browser preview and the DOCX renderer -- deliberately not reusing
either directly (one is TypeScript, the other targets python-docx's object
model), but all three read from identical source data, so what a teacher
sees in the browser is what ends up in both exports.

Font substitution (rule 31, documented not silent): "Times New Roman" is
declared in DocumentMeta as the default academic font, matching Word
convention, but Windows-licensed Times New Roman font files aren't legally
redistributable on Linux. Substituted with "DejaVu Serif" -- visually
verified (not assumed) to render all 9 Kazakh-specific Cyrillic letters
correctly, metrically a reasonable serif match.
"""
import base64
import html as html_escape

from app.documents.schemas import Block, DocumentModel, HeadingBlock, ImageBlock, ListBlock, PageBreakBlock, ParagraphBlock, Run, TableBlock

_FONT_SUBSTITUTIONS = {
    "times new roman": "DejaVu Serif",
}


def resolve_font_family(requested: str) -> str:
    return _FONT_SUBSTITUTIONS.get(requested.strip().lower(), requested)


def _esc(text: str) -> str:
    return html_escape.escape(text)


def _render_runs(runs: list[Run]) -> str:
    parts = []
    for run in runs:
        if run.kind == "text":
            text = _esc(run.text)
            if run.bold:
                text = f"<strong>{text}</strong>"
            if run.italic:
                text = f"<em>{text}</em>"
            if run.underline:
                text = f'<span style="text-decoration:underline">{text}</span>'
            parts.append(text)
        elif run.kind == "variable":
            parts.append(_esc(run.resolved_text or "{{" + run.key + "}}"))
        elif run.kind == "pageNumber":
            parts.append('<span class="pf-page-number-inline"></span>')
    return "".join(parts)


def _render_block(block: Block, load_image) -> str:
    if isinstance(block, ParagraphBlock):
        align = block.style_override.alignment if block.style_override else None
        style = f' style="text-align:{align}"' if align else ""
        return f'<p class="style-{block.style_name}"{style}>{_render_runs(block.runs)}</p>'
    if isinstance(block, HeadingBlock):
        return f"<h{block.level}>{_render_runs(block.runs)}</h{block.level}>"
    if isinstance(block, ImageBlock):
        if not block.file_id:
            return ""
        image_bytes = load_image(block.file_id)
        b64 = base64.b64encode(image_bytes).decode("ascii")
        width = f"{block.width_mm}mm" if block.width_mm else "100mm"
        caption_html = f"<figcaption>{_esc(block.caption)}</figcaption>" if block.caption else ""
        return (
            f'<figure style="text-align:{block.alignment}">'
            f'<img src="data:image/png;base64,{b64}" style="width:{width}" />'
            f"{caption_html}</figure>"
        )
    if isinstance(block, TableBlock):
        rows_html = "".join(
            "<tr>" + "".join(f"<td>{''.join(_render_block(b, load_image) for b in cell.blocks)}</td>" for cell in row.cells) + "</tr>"
            for row in block.rows
        )
        return f"<table>{rows_html}</table>"
    if isinstance(block, ListBlock):
        tag = "ol" if block.ordered else "ul"
        items_html = "".join(
            "<li>" + "".join(_render_block(b, load_image) for b in item.blocks) + "</li>" for item in block.items
        )
        return f"<{tag}>{items_html}</{tag}>"
    if isinstance(block, PageBreakBlock):
        return '<div class="pf-page-break"></div>'
    return ""


def _css_content_value(runs: list[Run]) -> str:
    """Builds a CSS `content:` value from a paragraph's runs -- text/variable
    runs become quoted string literals, a pageNumber run becomes counter(page),
    and CSS concatenates space-separated content parts automatically. This is
    what actually renders configured header/footer text in the @page margin
    box, rather than only ever showing a bare page number."""
    parts = []
    for run in runs:
        if run.kind == "text" and run.text:
            escaped = run.text.replace("\\", "\\\\").replace('"', '\\"')
            parts.append(f'"{escaped}"')
        elif run.kind == "variable":
            value = run.resolved_text or ("{{" + run.key + "}}")
            escaped = value.replace("\\", "\\\\").replace('"', '\\"')
            parts.append(f'"{escaped}"')
        elif run.kind == "pageNumber":
            parts.append("counter(page)")
    return " ".join(parts) if parts else '""'


def _first_paragraph_content(blocks: list[Block]) -> str:
    for block in blocks:
        if isinstance(block, ParagraphBlock):
            return _css_content_value(block.runs)
    return '""'


def build_html(document: DocumentModel, numbering: dict, load_image) -> str:
    font_family = resolve_font_family(document.meta.default_font)

    style_rules = []
    for name, style in document.meta.styles.items():
        rules = []
        if style.font_size_pt:
            rules.append(f"font-size:{style.font_size_pt}pt")
        if style.bold:
            rules.append("font-weight:bold")
        if style.italic:
            rules.append("font-style:italic")
        if style.alignment:
            rules.append(f"text-align:{style.alignment}")
        if style.line_spacing:
            rules.append(f"line-height:{style.line_spacing}")
        if style.first_line_indent_mm:
            rules.append(f"text-indent:{style.first_line_indent_mm}mm")
        if style.space_before_pt:
            rules.append(f"margin-top:{style.space_before_pt}pt")
        if style.space_after_pt is not None:
            rules.append(f"margin-bottom:{style.space_after_pt}pt")
        style_rules.append(f".style-{name} {{ {'; '.join(rules)} }}")

    title_page_html = ""
    if document.title_page:
        blocks_html = "".join(_render_block(b, load_image) for b in document.title_page.blocks)
        title_page_html = f'<section class="pf-title-page">{blocks_html}</section><div class="pf-page-break"></div>'

    sections_html = []
    for i, section in enumerate(document.sections):
        break_class = "pf-page-break-before" if (i > 0 and section.page_break_before) else ""
        blocks_html = "".join(_render_block(b, load_image) for b in section.blocks)
        sections_html.append(f'<section class="{break_class}"><h1>{_esc(section.title)}</h1>{blocks_html}</section>')

    margins = document.meta.margins
    page_size = "A4 landscape" if document.meta.orientation == "landscape" else "A4"

    footer_content = _first_paragraph_content(document.footer.blocks) if document.footer.enabled else None
    header_content = _first_paragraph_content(document.header.blocks) if document.header.enabled else None
    bottom_center_rule = f"content: {footer_content}; font-size: 10pt;" if footer_content else 'content: counter(page); font-size: 10pt;'
    top_center_rule = f"content: {header_content}; font-size: 10pt;" if header_content else ""

    return f"""<!DOCTYPE html>
<html lang="kk">
<head>
<meta charset="utf-8" />
<style>
  @page {{
    size: {page_size};
    margin-top: {margins.top_mm}mm;
    margin-bottom: {margins.bottom_mm}mm;
    margin-left: {margins.left_mm}mm;
    margin-right: {margins.right_mm}mm;
    @bottom-center {{ {bottom_center_rule} }}
    {f"@top-center {{ {top_center_rule} }}" if top_center_rule else ""}
  }}
  body {{
    font-family: "{font_family}", "DejaVu Serif", serif;
    font-size: {document.meta.default_font_size}pt;
    line-height: {document.meta.line_spacing};
    color: #000;
  }}
  h1 {{ font-size: 16pt; font-weight: bold; margin-top: 18pt; margin-bottom: 12pt; }}
  h2 {{ font-size: 14pt; font-weight: bold; margin-top: 12pt; margin-bottom: 8pt; }}
  h3 {{ font-size: 14pt; font-weight: bold; font-style: italic; margin-top: 8pt; margin-bottom: 6pt; }}
  p {{ margin: 0 0 8pt; text-align: justify; text-indent: 12.5mm; }}
  .pf-title-page p {{ text-align: center; text-indent: 0; }}
  table {{ border-collapse: collapse; width: 100%; margin: 8pt 0; }}
  td {{ border: 1px solid #000; padding: 4pt 6pt; vertical-align: top; }}
  figure {{ margin: 8pt 0; }}
  figure img {{ display: inline-block; }}
  figcaption {{ font-size: 12pt; font-style: italic; text-align: center; }}
  .pf-page-break, .pf-page-break-before {{ break-before: page; }}
  {" ".join(style_rules)}
</style>
</head>
<body>
{title_page_html}
{"".join(sections_html)}
</body>
</html>"""
