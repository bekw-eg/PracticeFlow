"""The structured document model (rule 2/3): every template version and every
report version stores exactly this shape in its `document_data` JSONB column.

Deliberately NOT free-form HTML and NOT a browser DOM serialization — this is
what lets the same document power the React editor, the read-only preview,
and (Phase 3) DOCX/PDF export without three divergent representations.

Every meaningful node carries a stable `id` (see node_ids.py), never an
array index, so Phase 3 comments can anchor to a specific node.
"""
from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

from app.documents.node_ids import new_node_id

# ---------------------------------------------------------------------------
# Page / typography configuration (rule 7, 8, 9)
# ---------------------------------------------------------------------------


class DocumentMargins(BaseModel):
    top_mm: float = 20
    bottom_mm: float = 20
    left_mm: float = 30
    right_mm: float = 10


class ParagraphStyle(BaseModel):
    """A named style (rule 9) or an inline override on a single block.

    `None` on any field means "inherit" — from the block's named style, or
    from the style's own defaults. This is what lets a paragraph override
    just `bold` without having to restate alignment/spacing/indentation.
    """

    alignment: Literal["left", "center", "right", "justify"] | None = None
    line_spacing: float | None = None
    space_before_pt: float | None = None
    space_after_pt: float | None = None
    first_line_indent_mm: float | None = None
    left_indent_mm: float | None = None
    right_indent_mm: float | None = None
    font_family: str | None = None
    font_size_pt: int | None = None
    bold: bool | None = None
    italic: bool | None = None
    underline: bool | None = None


def _default_styles() -> dict[str, ParagraphStyle]:
    """The fixed style catalog (rule 9): Normal, Title, Subtitle, Heading 1-3,
    Caption. A document's blocks reference these by name rather than each
    repeating full formatting — the standard "styles" concept from
    word-processing documents, kept structural instead of duplicated."""
    return {
        "Normal": ParagraphStyle(alignment="justify", line_spacing=1.5, first_line_indent_mm=12.5),
        "Title": ParagraphStyle(alignment="center", font_size_pt=16, bold=True, space_after_pt=12),
        "Subtitle": ParagraphStyle(alignment="center", font_size_pt=14, space_after_pt=12),
        "Heading1": ParagraphStyle(alignment="left", font_size_pt=16, bold=True, space_before_pt=18, space_after_pt=12, first_line_indent_mm=0),
        "Heading2": ParagraphStyle(alignment="left", font_size_pt=14, bold=True, space_before_pt=12, space_after_pt=8, first_line_indent_mm=0),
        "Heading3": ParagraphStyle(alignment="left", font_size_pt=14, bold=True, italic=True, space_before_pt=8, space_after_pt=6, first_line_indent_mm=0),
        "Caption": ParagraphStyle(alignment="center", font_size_pt=12, italic=True, space_before_pt=4),
    }


class NumberingConfig(BaseModel):
    """Rule 12/13: automatic, structural numbering — never typed by hand."""

    enabled: bool = True
    start_number: int = 1
    style: Literal["decimal"] = "decimal"


class DocumentMeta(BaseModel):
    page_size: Literal["A4"] = "A4"
    orientation: Literal["portrait", "landscape"] = "portrait"
    margins: DocumentMargins = Field(default_factory=DocumentMargins)
    default_font: str = "Times New Roman"
    default_font_size: int = 14
    line_spacing: float = 1.5
    styles: dict[str, ParagraphStyle] = Field(default_factory=_default_styles)
    numbering: NumberingConfig = Field(default_factory=NumberingConfig)


# ---------------------------------------------------------------------------
# Inline runs (the content of a paragraph/heading)
# ---------------------------------------------------------------------------


class TextRun(BaseModel):
    kind: Literal["text"] = "text"
    id: str = Field(default_factory=lambda: new_node_id("run"))
    text: str = ""
    bold: bool = False
    italic: bool = False
    underline: bool = False


class VariableRun(BaseModel):
    """Rule 17/18: a system variable placeholder, e.g. {{student.full_name}}.
    `resolved_text` is never persisted — it's populated only in read
    responses by the variable resolution service (app/documents/variables.py)."""

    kind: Literal["variable"] = "variable"
    id: str = Field(default_factory=lambda: new_node_id("var"))
    key: str
    resolved_text: str | None = None


class PageNumberRun(BaseModel):
    """Rule 21: structural page-number placeholder for headers/footers.
    Final pagination is a Phase 3 DOCX/PDF concern; the browser preview may
    show an approximate page number where feasible."""

    kind: Literal["pageNumber"] = "pageNumber"
    id: str = Field(default_factory=lambda: new_node_id("pn"))


Run = Annotated[Union[TextRun, VariableRun, PageNumberRun], Field(discriminator="kind")]

# ---------------------------------------------------------------------------
# Block nodes
# ---------------------------------------------------------------------------


class HeadingNumbering(BaseModel):
    participates: bool = True


class ParagraphBlock(BaseModel):
    type: Literal["paragraph"] = "paragraph"
    id: str = Field(default_factory=lambda: new_node_id("p"))
    style_name: str = "Normal"
    style_override: ParagraphStyle | None = None
    runs: list[Run] = Field(default_factory=list)


class HeadingBlock(BaseModel):
    type: Literal["heading"] = "heading"
    id: str = Field(default_factory=lambda: new_node_id("h"))
    level: int = Field(default=1, ge=1, le=3)
    style_name: str | None = None  # defaults to "Heading{level}" if unset
    runs: list[Run] = Field(default_factory=list)
    numbering: HeadingNumbering = Field(default_factory=HeadingNumbering)


class ImageBlock(BaseModel):
    type: Literal["image"] = "image"
    id: str = Field(default_factory=lambda: new_node_id("img"))
    file_id: str | None = None
    width_mm: float | None = None
    alignment: Literal["left", "center", "right"] = "center"
    caption: str = ""


class PageBreakBlock(BaseModel):
    type: Literal["pageBreak"] = "pageBreak"
    id: str = Field(default_factory=lambda: new_node_id("brk"))


class TableCell(BaseModel):
    id: str = Field(default_factory=lambda: new_node_id("cell"))
    blocks: list["Block"] = Field(default_factory=list)


class TableRow(BaseModel):
    id: str = Field(default_factory=lambda: new_node_id("row"))
    cells: list[TableCell] = Field(default_factory=list)


class TableBlock(BaseModel):
    type: Literal["table"] = "table"
    id: str = Field(default_factory=lambda: new_node_id("tbl"))
    rows: list[TableRow] = Field(default_factory=list)


class ListItem(BaseModel):
    id: str = Field(default_factory=lambda: new_node_id("li"))
    blocks: list["Block"] = Field(default_factory=list)


class ListBlock(BaseModel):
    type: Literal["list"] = "list"
    id: str = Field(default_factory=lambda: new_node_id("list"))
    ordered: bool = False
    items: list[ListItem] = Field(default_factory=list)


Block = Annotated[
    Union[ParagraphBlock, HeadingBlock, ImageBlock, PageBreakBlock, TableBlock, ListBlock],
    Field(discriminator="type"),
]

TableCell.model_rebuild()
ListItem.model_rebuild()

# ---------------------------------------------------------------------------
# Sections, title page, header/footer, document root
# ---------------------------------------------------------------------------


class SectionNumbering(BaseModel):
    participates: bool = True


class Section(BaseModel):
    """Rule 14: teacher-defined structural sections (Introduction, Chapter 1, ...).

    `required` + `editable` together implement rule 16's LOCKED vs EDITABLE
    split: a required section can't be deleted by a student; a
    non-editable section's blocks can't be touched by a student at all
    (the student PATCH endpoint only accepts edits to sections where
    editable=True — see app/services/report_document_service.py).
    """

    id: str = Field(default_factory=lambda: new_node_id("sec"))
    key: str = ""
    title: str = ""
    level: int = Field(default=1, ge=1, le=3)
    required: bool = False
    editable: bool = True
    page_break_before: bool = False
    numbering: SectionNumbering = Field(default_factory=SectionNumbering)
    blocks: list[Block] = Field(default_factory=list)


class TitlePage(BaseModel):
    blocks: list[Block] = Field(default_factory=list)


class HeaderFooter(BaseModel):
    enabled: bool = False
    blocks: list[Block] = Field(default_factory=list)


class DocumentModel(BaseModel):
    schema_version: int = 1
    meta: DocumentMeta = Field(default_factory=DocumentMeta)
    title_page: TitlePage | None = None
    header: HeaderFooter = Field(default_factory=HeaderFooter)
    footer: HeaderFooter = Field(default_factory=HeaderFooter)
    sections: list[Section] = Field(default_factory=list)

    def find_section(self, section_id: str) -> Section | None:
        for section in self.sections:
            if section.id == section_id:
                return section
        return None


DocumentModel.model_rebuild()
