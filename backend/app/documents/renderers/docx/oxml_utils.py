"""The ONE place raw OOXML manipulation happens in the whole project (rule
25: 'do not scatter raw XML manipulation throughout the project'). Used only
for the one thing python-docx's high-level API genuinely can't do: a real
Word page-number FIELD (not a static number baked into text), which updates
itself as Word paginates the document.
"""
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.text.paragraph import Paragraph


def add_page_number_field(paragraph: Paragraph) -> None:
    """Inserts a real { PAGE } field code into the paragraph -- Word computes
    and displays the actual page number when the document is opened/printed,
    exactly like a native Word page-number footer, not a static digit."""
    run = paragraph.add_run()

    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")

    instr_text = OxmlElement("w:instrText")
    instr_text.set(qn("xml:space"), "preserve")
    instr_text.text = "PAGE"

    fld_separate = OxmlElement("w:fldChar")
    fld_separate.set(qn("w:fldCharType"), "separate")

    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")

    run._r.append(fld_begin)
    run._r.append(instr_text)
    run._r.append(fld_separate)
    run._r.append(fld_end)


def clear_theme_font_and_color(word_style) -> None:
    """python-docx's `font.name = ...` sets `w:rFonts/@w:ascii` but leaves
    any pre-existing `w:asciiTheme`/`w:eastAsiaTheme`/`w:hAnsiTheme`/
    `w:cstheme` attributes in place. When both are present, Word AND
    LibreOffice prioritize the THEME reference, silently ignoring the
    explicit font -- confirmed by rendering and visually inspecting the
    output (Times New Roman was set but a theme sans-serif font still
    rendered). This strips the theme references so the explicit font
    actually wins, and clears any theme text color (Word's built-in
    Title/Subtitle styles default to a decorative theme blue, inappropriate
    for a formal academic report where black body/heading text is expected).
    """
    rpr = word_style.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is not None:
        for attr in ("asciiTheme", "eastAsiaTheme", "hAnsiTheme", "cstheme"):
            key = qn(f"w:{attr}")
            if rfonts.get(key) is not None:
                del rfonts.attrib[key]
    color = rpr.find(qn("w:color"))
    if color is not None:
        color.set(qn("w:val"), "000000")
        theme_color_key = qn("w:themeColor")
        if color.get(theme_color_key) is not None:
            del color.attrib[theme_color_key]
