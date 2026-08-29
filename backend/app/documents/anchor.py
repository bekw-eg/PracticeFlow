"""Comment anchor validation (rule 12). A comment anchors to a stable
node_id + character offsets + a text snapshot taken at creation time. This
module re-checks that anchor against the CURRENT document content — never
stored durably, always recomputed at read time, so it's never stale.

Deliberately conservative: if anything about the anchor can't be verified
with confidence, the comment is marked invalid rather than guessed at. No
fuzzy matching, no "closest text" heuristics — those are exactly the kind
of fragile hack rule 12 warns against.
"""
from dataclasses import dataclass
from typing import Literal

from app.documents.schemas import Block, DocumentModel, HeadingBlock, ListBlock, ParagraphBlock, TableBlock

AnchorStatus = Literal["valid", "invalid"]


@dataclass
class AnchorCheckResult:
    status: AnchorStatus
    current_text: str | None


def _find_node_text(blocks: list[Block], node_id: str) -> str | None:
    """Concatenated plain text of the target paragraph/heading, or None if
    no such node exists anywhere in the tree (including nested inside
    table cells and list items)."""
    for block in blocks:
        if block.id == node_id and isinstance(block, (ParagraphBlock, HeadingBlock)):
            return "".join(run.text for run in block.runs if run.kind == "text")
        if isinstance(block, TableBlock):
            for row in block.rows:
                for cell in row.cells:
                    found = _find_node_text(cell.blocks, node_id)
                    if found is not None:
                        return found
        if isinstance(block, ListBlock):
            for item in block.items:
                found = _find_node_text(item.blocks, node_id)
                if found is not None:
                    return found
    return None


def check_anchor(document: DocumentModel, node_id: str, start_offset: int, end_offset: int, text_snapshot: str) -> AnchorCheckResult:
    all_blocks: list[Block] = []
    for section in document.sections:
        all_blocks.extend(section.blocks)
    if document.title_page:
        all_blocks.extend(document.title_page.blocks)

    current_text = _find_node_text(all_blocks, node_id)

    if current_text is None:
        return AnchorCheckResult(status="invalid", current_text=None)

    if start_offset < 0 or end_offset > len(current_text) or start_offset >= end_offset:
        return AnchorCheckResult(status="invalid", current_text=current_text)

    live_slice = current_text[start_offset:end_offset]
    if live_slice != text_snapshot:
        return AnchorCheckResult(status="invalid", current_text=current_text)

    return AnchorCheckResult(status="valid", current_text=current_text)
