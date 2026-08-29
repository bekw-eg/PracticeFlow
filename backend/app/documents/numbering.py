"""Automatic numbering (rule 12/13). Numbers are never stored as text — they
are computed fresh from document structure every time the document is read,
so inserting/removing/reordering sections never requires renumbering by hand.
"""
from app.documents.schemas import DocumentModel, HeadingBlock


def compute_numbering(document: DocumentModel) -> dict[str, str]:
    """Returns {node_id: '2.1'} for every section/heading that participates
    in numbering. Top-level sections are numbered sequentially starting at
    `meta.numbering.start_number`; headings inside a section are numbered
    `{section_number}.{n}` per heading level, restarting the counter at each
    level boundary (Word-style outline numbering)."""
    result: dict[str, str] = {}
    if not document.meta.numbering.enabled:
        return result

    section_counter = document.meta.numbering.start_number
    for section in document.sections:
        if not section.numbering.participates:
            continue
        section_number = str(section_counter)
        result[section.id] = section_number
        section_counter += 1

        # level -> current counter at that level, reset whenever a shallower
        # level advances (e.g. a new level-1 heading resets any level-2 counter).
        level_counters: dict[int, int] = {}
        _number_headings(section.blocks, section_number, level_counters, result)

    return result


def _number_headings(blocks: list, prefix: str, level_counters: dict[int, int], result: dict[str, str]) -> None:
    for block in blocks:
        if isinstance(block, HeadingBlock):
            if not block.numbering.participates:
                continue
            level = block.level
            # Reset deeper levels whenever a shallower or equal level advances.
            for deeper in [lvl for lvl in level_counters if lvl > level]:
                del level_counters[deeper]
            level_counters[level] = level_counters.get(level, 0) + 1

            parts = [prefix] + [str(level_counters[lvl]) for lvl in sorted(level_counters)]
            result[block.id] = ".".join(parts)
        # Table/list cells can theoretically nest headings in a rich editor,
        # but Phase 2 doesn't allow inserting headings inside them — nothing
        # further to recurse into here for now.
