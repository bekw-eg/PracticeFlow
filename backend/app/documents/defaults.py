"""Factory for a new template version's starting content (rule 46's scenario:
Title Page / Introduction / Chapter 1-3 / Conclusion / References).

This is a starting point, not a hardcoded limitation — the teacher can
rename, reorder, add, or remove sections freely in the editor afterward.
"""
from app.documents.schemas import DocumentModel, ParagraphBlock, Section, TextRun, TitlePage, VariableRun


def build_default_document() -> DocumentModel:
    title_page = TitlePage(
        blocks=[
            ParagraphBlock(style_name="Subtitle", runs=[VariableRun(key="organization.name")]),
            ParagraphBlock(style_name="Title", runs=[TextRun(text="ОТЧЁТ")]),
            ParagraphBlock(style_name="Subtitle", runs=[VariableRun(key="internship.title")]),
            ParagraphBlock(runs=[TextRun(text="Выполнил(а): "), VariableRun(key="student.full_name")]),
            ParagraphBlock(runs=[TextRun(text="Группа: "), VariableRun(key="student.group")]),
            ParagraphBlock(runs=[TextRun(text="Руководитель: "), VariableRun(key="teacher.full_name")]),
            ParagraphBlock(style_name="Subtitle", runs=[VariableRun(key="academic_year")]),
        ]
    )

    def chapter(key: str, title: str) -> Section:
        return Section(
            key=key,
            title=title,
            level=1,
            required=True,
            editable=True,
            page_break_before=True,
            # The Section itself carries the chapter number and title (rendered
            # as "{number} {title}" by the frontend) — no HeadingBlock needed
            # here. A HeadingBlock inside `blocks` is for a SUB-heading within
            # the chapter (numbered "{n}.1", "{n}.2", ...), which the teacher
            # adds explicitly rather than one being pre-seeded and duplicating
            # the section's own title/number.
            blocks=[ParagraphBlock(runs=[TextRun(text="")])],
        )

    sections = [
        chapter("introduction", "Введение"),
        chapter("chapter_1", "Глава 1"),
        chapter("chapter_2", "Глава 2"),
        chapter("chapter_3", "Глава 3"),
        chapter("conclusion", "Заключение"),
        chapter("references", "Список использованных источников"),
    ]

    return DocumentModel(title_page=title_page, sections=sections)
