"""Maps our named ParagraphStyle catalog (DocumentMeta.styles) onto real
Word paragraph styles, so the exported DOCX has genuine Word styles a user
could see/modify in Word's Styles pane -- not just visually-similar
formatting baked into every paragraph individually.
"""
from docx.document import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Mm, Pt
from docx.styles.style import _ParagraphStyle

from app.documents.renderers.docx.oxml_utils import clear_theme_font_and_color
from app.documents.schemas import DocumentMeta, ParagraphStyle

_ALIGNMENT_MAP = {
    "left": WD_ALIGN_PARAGRAPH.LEFT,
    "center": WD_ALIGN_PARAGRAPH.CENTER,
    "right": WD_ALIGN_PARAGRAPH.RIGHT,
    "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
}


def apply_paragraph_style(word_style: _ParagraphStyle, style: ParagraphStyle, meta: DocumentMeta) -> None:
    font = word_style.font
    font.name = style.font_family or meta.default_font
    font.size = Pt(style.font_size_pt or meta.default_font_size)
    font.bold = bool(style.bold)
    font.italic = bool(style.italic)
    font.underline = bool(style.underline)
    clear_theme_font_and_color(word_style)

    fmt = word_style.paragraph_format
    fmt.alignment = _ALIGNMENT_MAP.get(style.alignment or "left")
    fmt.line_spacing = style.line_spacing or meta.line_spacing
    fmt.space_before = Pt(style.space_before_pt or 0)
    fmt.space_after = Pt(style.space_after_pt or 0)
    if style.first_line_indent_mm:
        fmt.first_line_indent = Mm(style.first_line_indent_mm)
    if style.left_indent_mm:
        fmt.left_indent = Mm(style.left_indent_mm)
    if style.right_indent_mm:
        fmt.right_indent = Mm(style.right_indent_mm)


def register_document_styles(doc: Document, meta: DocumentMeta) -> None:
    """Overwrites the built-in Word styles our named styles map to (Normal,
    Title, Heading 1-3, Caption) with the teacher's configured formatting,
    so every paragraph that references e.g. 'Heading1' picks it up
    automatically rather than needing per-paragraph overrides."""
    word_style_names = {
        "Normal": "Normal",
        "Title": "Title",
        "Subtitle": "Subtitle",
        "Heading1": "Heading 1",
        "Heading2": "Heading 2",
        "Heading3": "Heading 3",
        "Caption": "Caption",
    }
    for our_name, word_name in word_style_names.items():
        our_style = meta.styles.get(our_name)
        if our_style is None:
            continue
        try:
            word_style = doc.styles[word_name]
        except KeyError:
            continue
        if word_style.type != 1:  # WD_STYLE_TYPE.PARAGRAPH
            continue
        apply_paragraph_style(word_style, our_style, meta)
