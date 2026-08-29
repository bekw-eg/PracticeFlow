"""Renders our Block tree into real python-docx paragraphs/tables/images.
This is the DOCX-specific leaf of the SAME structured document model that
powers the browser editor -- never HTML, never a DOM, never a screenshot
(rule 21).

Structural numbering is an editor-only aid. Exported headings contain only
their authored runs: no generated prefix, Word numbering field, or heading
style numbering is added here. A number a teacher typed into the heading
itself remains an ordinary TextRun and is therefore preserved.
"""
import io
from collections.abc import Callable

from docx.document import Document
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Mm
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.documents.renderers.docx.oxml_utils import add_page_number_field
from app.documents.schemas import (
    Block,
    HeadingBlock,
    ImageBlock,
    ListBlock,
    PageBreakBlock,
    ParagraphBlock,
    Run,
    TableBlock,
)

ImageLoader = Callable[[str], bytes]

_ALIGNMENT_MAP = {
    "left": WD_ALIGN_PARAGRAPH.LEFT,
    "center": WD_ALIGN_PARAGRAPH.CENTER,
    "right": WD_ALIGN_PARAGRAPH.RIGHT,
    "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
}


def _apply_runs(paragraph: Paragraph, runs: list[Run]) -> None:
    for run in runs:
        if run.kind == "text":
            r = paragraph.add_run(run.text)
            r.bold = run.bold or None
            r.italic = run.italic or None
            r.underline = run.underline or None
        elif run.kind == "variable":
            # Variables must already be resolved before rendering reaches
            # here (see renderer.py) -- resolved_text is the source, the
            # {{key}} placeholder must never leak into a final export.
            paragraph.add_run(run.resolved_text or "")
        elif run.kind == "pageNumber":
            add_page_number_field(paragraph)


def render_paragraph(doc: Document, block: ParagraphBlock) -> Paragraph:
    paragraph = doc.add_paragraph(style=block.style_name if block.style_name in doc.styles else "Normal")
    _apply_runs(paragraph, block.runs)
    if block.style_override and block.style_override.alignment:
        paragraph.alignment = _ALIGNMENT_MAP.get(block.style_override.alignment)
    return paragraph


def render_heading(doc: Document, block: HeadingBlock) -> Paragraph:
    style_name = f"Heading {block.level}"
    paragraph = doc.add_paragraph(style=style_name if style_name in doc.styles else "Heading 1")
    _apply_runs(paragraph, block.runs)
    return paragraph


def render_table(doc: Document, block: TableBlock) -> Table:
    if not block.rows:
        return doc.add_table(rows=0, cols=0)
    n_cols = len(block.rows[0].cells)
    table = doc.add_table(rows=len(block.rows), cols=n_cols)
    table.style = "Table Grid"
    for row_idx, row in enumerate(block.rows):
        for col_idx, cell in enumerate(row.cells):
            if col_idx >= n_cols:
                continue
            docx_cell = table.cell(row_idx, col_idx)
            docx_cell.vertical_alignment = WD_ALIGN_VERTICAL.TOP
            first = True
            for cell_block in cell.blocks:
                if cell_block.type == "paragraph":
                    if first:
                        docx_cell.paragraphs[0].text = ""
                        _apply_runs(docx_cell.paragraphs[0], cell_block.runs)
                        first = False
                    else:
                        p = docx_cell.add_paragraph()
                        _apply_runs(p, cell_block.runs)
    return table


def render_image(doc: Document, block: ImageBlock, load_image: ImageLoader) -> None:
    if not block.file_id:
        return
    image_bytes = load_image(block.file_id)
    width = Mm(block.width_mm) if block.width_mm else Mm(100)
    paragraph = doc.add_paragraph()
    paragraph.alignment = _ALIGNMENT_MAP.get(block.alignment, WD_ALIGN_PARAGRAPH.CENTER)
    run = paragraph.add_run()
    run.add_picture(io.BytesIO(image_bytes), width=width)
    if block.caption:
        caption_p = doc.add_paragraph(style="Caption" if "Caption" in doc.styles else "Normal")
        caption_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        caption_p.add_run(block.caption)


def render_list(doc: Document, block: ListBlock) -> None:
    style_name = "List Number" if block.ordered else "List Bullet"
    for item in block.items:
        for item_block in item.blocks:
            if item_block.type == "paragraph":
                paragraph = doc.add_paragraph(style=style_name if style_name in doc.styles else "Normal")
                _apply_runs(paragraph, item_block.runs)


def render_block(doc: Document, block: Block, load_image: ImageLoader) -> None:
    if isinstance(block, ParagraphBlock):
        render_paragraph(doc, block)
    elif isinstance(block, HeadingBlock):
        render_heading(doc, block)
    elif isinstance(block, TableBlock):
        render_table(doc, block)
    elif isinstance(block, ImageBlock):
        render_image(doc, block, load_image)
    elif isinstance(block, ListBlock):
        render_list(doc, block)
    elif isinstance(block, PageBreakBlock):
        doc.add_page_break()
