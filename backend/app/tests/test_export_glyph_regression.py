"""Regression coverage for Kazakh glyphs in the two export renderers.

The document text is intentionally authored data, not a UI translation.  The
tests assert byte-for-byte preservation in DOCX and render the PDF all the way
to a bitmap when Poppler is available.
"""
import io
import shutil
import subprocess
from pathlib import Path

import docx
import pytest
from docx.oxml.ns import qn
from PIL import Image, ImageChops

from app.documents.numbering import compute_numbering
from app.documents.renderers.docx.renderer import render_docx
from app.documents.renderers.pdf.html_builder import build_html
from app.documents.schemas import DocumentModel, ParagraphBlock, Section, TextRun

KAZAKH_GLYPH_SAMPLE = "Әліпби: ә ғ қ ң ө ұ ү һ і"


def _glyph_document() -> DocumentModel:
    return DocumentModel(
        sections=[
            Section(
                title="Қазақша глифтер",
                blocks=[ParagraphBlock(runs=[TextRun(text=KAZAKH_GLYPH_SAMPLE)])],
            )
        ]
    )


def _pdf_text(payload: bytes) -> str:
    pypdf = pytest.importorskip("pypdf")
    return "\n".join(page.extract_text() or "" for page in pypdf.PdfReader(io.BytesIO(payload)).pages)


def _assert_pdf_page_has_visible_ink(payload: bytes, tmp_path: Path) -> None:
    """Rasterize the generated page so this also covers visible glyph output."""
    pdftoppm = shutil.which("pdftoppm")
    if pdftoppm is None:
        pytest.skip("pdftoppm is required for the visual PDF glyph regression check")

    pdf_path = tmp_path / "kazakh-glyphs.pdf"
    png_prefix = tmp_path / "kazakh-glyphs"
    pdf_path.write_bytes(payload)
    subprocess.run([pdftoppm, "-f", "1", "-l", "1", "-png", str(pdf_path), str(png_prefix)], check=True)
    rendered = tmp_path / "kazakh-glyphs-1.png"
    assert rendered.exists()
    with Image.open(rendered) as image:
        # A non-empty bitmap is a rendering-level guard against the entire
        # Kazakh line disappearing because no usable font was found.
        assert ImageChops.invert(image.convert("L")).getbbox() is not None


def test_pdf_html_language_is_document_metadata_with_a_neutral_fallback():
    document = _glyph_document()

    assert '<html lang="und">' in build_html(document, compute_numbering(document), lambda _file_id: b"")
    assert '<html lang="en-US">' in build_html(
        document,
        compute_numbering(document),
        lambda _file_id: b"",
        document_language="en-US",
    )
    assert '<html lang="und">' in build_html(
        document,
        compute_numbering(document),
        lambda _file_id: b"",
        document_language='kk" onload="alert(1)',
    )


def test_pdf_kazakh_glyph_regression_renders_unicode_text(tmp_path: Path):
    try:
        from app.documents.renderers.pdf.renderer import render_pdf
    except (ImportError, OSError) as error:
        pytest.skip(f"WeasyPrint native renderer is unavailable: {error}")

    document = _glyph_document()
    payload = render_pdf(document, compute_numbering(document), lambda _file_id: b"").getvalue()

    assert KAZAKH_GLYPH_SAMPLE in _pdf_text(payload)
    _assert_pdf_page_has_visible_ink(payload, tmp_path)


def test_docx_preserves_kazakh_glyphs_and_sets_word_font_slots():
    document = _glyph_document()
    payload = render_docx(document, compute_numbering(document), lambda _file_id: b"").getvalue()
    exported = docx.Document(io.BytesIO(payload))

    assert KAZAKH_GLYPH_SAMPLE in "\n".join(paragraph.text for paragraph in exported.paragraphs)
    normal_rfonts = exported.styles["Normal"].element.xpath("./w:rPr/w:rFonts")[0]
    assert all(normal_rfonts.get(qn(f"w:{slot}")) == "Times New Roman" for slot in ("ascii", "hAnsi", "eastAsia", "cs"))


@pytest.mark.skipif(shutil.which("soffice") is None, reason="LibreOffice is not installed in this test environment")
def test_docx_kazakh_glyph_regression_renders_in_libreoffice(tmp_path: Path):
    """LibreOffice provides the visual smoke test; OOXML slots cover Word."""
    document = _glyph_document()
    docx_path = tmp_path / "kazakh-glyphs.docx"
    output_dir = tmp_path / "rendered"
    profile_dir = tmp_path / "libreoffice-profile"
    output_dir.mkdir()
    profile_dir.mkdir()
    docx_path.write_bytes(render_docx(document, compute_numbering(document), lambda _file_id: b"").getvalue())

    result = subprocess.run(
        [
            shutil.which("soffice") or "soffice",
            "--headless",
            f"-env:UserInstallation={profile_dir.as_uri()}",
            "--convert-to",
            "pdf",
            "--outdir",
            str(output_dir),
            str(docx_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    pdf_path = output_dir / "kazakh-glyphs.pdf"
    assert pdf_path.exists(), result.stderr
    payload = pdf_path.read_bytes()
    assert KAZAKH_GLYPH_SAMPLE in _pdf_text(payload)
    _assert_pdf_page_has_visible_ink(payload, tmp_path)
