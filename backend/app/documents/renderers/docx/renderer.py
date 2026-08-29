"""Main DOCX rendering entrypoint (rule 21/22). Deliberately takes no DB
session, no FastAPI request, no repositories -- only the resolved document,
its numbering, and an image-loading callback the caller injects. This is
what keeps the renderer isolated and independently testable (rule 22).
"""
import io

import docx
from docx.enum.section import WD_ORIENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Mm

from app.documents.renderers.docx.blocks import ImageLoader, render_block
from app.documents.renderers.docx.oxml_utils import add_page_number_field
from app.documents.renderers.docx.styles import register_document_styles
from app.documents.schemas import DocumentModel


def render_docx(document: DocumentModel, numbering: dict[str, str], load_image: ImageLoader) -> io.BytesIO:
    """`document` must already have variables resolved (VariableRun.resolved_text
    populated) -- see app/documents/variables.py. This function never
    resolves variables itself; rendering and resolution are separate
    concerns."""
    doc = docx.Document()
    register_document_styles(doc, document.meta)

    section = doc.sections[0]
    section.page_height = Mm(297) if document.meta.orientation == "portrait" else Mm(210)
    section.page_width = Mm(210) if document.meta.orientation == "portrait" else Mm(297)
    section.orientation = WD_ORIENT.PORTRAIT if document.meta.orientation == "portrait" else WD_ORIENT.LANDSCAPE
    section.top_margin = Mm(document.meta.margins.top_mm)
    section.bottom_margin = Mm(document.meta.margins.bottom_mm)
    section.left_margin = Mm(document.meta.margins.left_mm)
    section.right_margin = Mm(document.meta.margins.right_mm)

    if document.footer.enabled:
        footer_paragraph = section.footer.paragraphs[0]
        footer_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for block in document.footer.blocks:
            if block.type == "paragraph":
                for run in block.runs:
                    if run.kind == "pageNumber":
                        add_page_number_field(footer_paragraph)
                    elif run.kind == "text":
                        footer_paragraph.add_run(run.text)
                    elif run.kind == "variable":
                        footer_paragraph.add_run(run.resolved_text or "")
    if document.header.enabled:
        header_paragraph = section.header.paragraphs[0]
        for block in document.header.blocks:
            if block.type == "paragraph":
                for run in block.runs:
                    if run.kind == "text":
                        header_paragraph.add_run(run.text)
                    elif run.kind == "variable":
                        header_paragraph.add_run(run.resolved_text or "")

    if document.title_page:
        for block in document.title_page.blocks:
            if block.type == "paragraph":
                render_block(doc, block, load_image)
        doc.add_page_break()

    for i, doc_section in enumerate(document.sections):
        if i > 0 and doc_section.page_break_before:
            doc.add_page_break()

        heading_style = "Heading 1"
        heading_paragraph = doc.add_paragraph(style=heading_style if heading_style in doc.styles else None)
        heading_paragraph.add_run(doc_section.title)

        for block in doc_section.blocks:
            render_block(doc, block, load_image)

    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer
