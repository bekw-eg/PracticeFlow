"""Main PDF rendering entrypoint (rule 29/30). Same isolation principle as
the DOCX renderer (rule 22): no DB session, no FastAPI request -- only the
resolved document, its numbering, and an injected image loader.

WeasyPrint chosen over a DOCX->converter pipeline (rule 29 explicitly warns
against unevaluated fidelity from that path): it renders directly from
HTML+CSS using a real CSS Paged Media implementation (supports @page
margins, break-before, and counter(page) for genuine page numbers -- not
static digits), and was already verified working in this environment,
including full Kazakh Cyrillic glyph coverage via DejaVu Serif.
"""
import io

from weasyprint import HTML

from app.documents.renderers.docx.blocks import ImageLoader
from app.documents.renderers.pdf.html_builder import build_html
from app.documents.schemas import DocumentModel


def render_pdf(document: DocumentModel, numbering: dict, load_image: ImageLoader) -> io.BytesIO:
    """`document` must already have variables resolved -- same contract as
    render_docx, so both renderers stay in lockstep on that responsibility."""
    html_content = build_html(document, numbering, load_image)
    buffer = io.BytesIO()
    HTML(string=html_content).write_pdf(buffer)
    buffer.seek(0)
    return buffer
