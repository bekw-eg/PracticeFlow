"""Apply a frozen browser preview layout without guessing Word page boundaries.

Only numeric source locations are stored, never excerpts. Formatting belongs to
an entire paragraph/run, so a unit shared with an included page remains checked.
Unmapped content also remains checked.
"""
from __future__ import annotations

from collections import defaultdict

from app.schemas.document_check import DocumentPageExclusions


class PageExclusionScope:
    def __init__(self, exclusions=None):
        parsed = DocumentPageExclusions.model_validate(exclusions or {})
        self.excluded = set(parsed.pages)
        self.locations = defaultdict(set)
        for page in parsed.layout:
            for paragraph, runs in page.paragraphs.items():
                if runs:
                    self.locations[("section", page.section_index)].add(page.number)
                    self.locations[("paragraph", int(paragraph))].add(page.number)
                for run in runs:
                    self.locations[("run", int(paragraph), run)].add(page.number)

    def included_pages(self, location):
        if not self.excluded:
            return None
        if "run_index" in location:
            key = ("run", location.get("paragraph_index"), location["run_index"])
        elif "paragraph_index" in location:
            key = ("paragraph", location["paragraph_index"])
        else:
            key = ("section", location.get("section_index"))
        pages = self.locations.get(key)
        return sorted(pages - self.excluded) if pages else None


def validate_preview_locations(exclusions: DocumentPageExclusions, html: str):
    """Reject source indexes that do not belong to the authorized original."""
    from lxml import html as lhtml
    root = lhtml.fragment_fromstring(html, create_parent=True)
    valid = defaultdict(dict)
    required = defaultdict(dict)
    for section in root.xpath('.//section[@data-section-index]'):
        section_index = int(section.get("data-section-index"))
        for paragraph in section.xpath('.//*[@data-paragraph-index]'):
            valid[section_index][paragraph.get("data-paragraph-index")] = {
                int(run.get("data-run-index")) for run in paragraph.xpath('.//*[@data-run-index]')}
            runs = {int(run.get("data-run-index")) for run in paragraph.xpath('.//*[@data-run-index]')
                    if any(node.text_content().strip() or node.get("data-check-image") is not None
                           for node in run.xpath('.//*[@data-check-text or @data-check-image][not(@data-check-excluded="true")]'))}
            if runs:
                required[section_index][paragraph.get("data-paragraph-index")] = runs
    for page in exclusions.layout:
        if page.section_index not in valid:
            raise ValueError("Unknown preview section")
        for paragraph, runs in page.paragraphs.items():
            if paragraph not in valid[page.section_index] or set(runs) - valid[page.section_index][paragraph]:
                raise ValueError("Unknown preview paragraph or run")
    # A partial map could accidentally hide the continuation of a paragraph.
    mapped = defaultdict(set)
    for page in exclusions.layout:
        for paragraph, runs in page.paragraphs.items():
            mapped[(page.section_index, paragraph)].update(runs)
    for section, paragraphs in required.items():
        for paragraph, runs in paragraphs.items():
            if (section, paragraph) not in mapped or runs - mapped[(section, paragraph)]:
                raise ValueError("Preview layout must include every source paragraph and run")
