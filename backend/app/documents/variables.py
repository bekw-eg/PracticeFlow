"""System variable resolution (rule 17/18). This is the ONLY place variable
values get computed — never inline in a React component, never duplicated
elsewhere. Phase 3's DOCX/PDF renderers will call the same function.

Resolution never mutates the stored document: it returns a deep copy with
`VariableRun.resolved_text` populated, so the persisted document_data keeps
the {{key}} reference forever (correct even if, say, an org is renamed).
"""
from dataclasses import dataclass

from app.documents.schemas import Block, DocumentModel, HeadingBlock, ListBlock, ParagraphBlock, TableBlock, VariableRun


@dataclass
class VariableContext:
    organization_name: str = ""
    student_full_name: str = ""
    student_group: str = ""
    student_specialty: str = ""
    student_department: str = ""
    teacher_full_name: str = ""
    internship_title: str = ""
    internship_start_date: str = ""
    internship_end_date: str = ""
    academic_year: str = ""
    current_year: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "organization.name": self.organization_name,
            "student.full_name": self.student_full_name,
            "student.group": self.student_group,
            "student.specialty": self.student_specialty,
            "student.department": self.student_department,
            "teacher.full_name": self.teacher_full_name,
            "internship.title": self.internship_title,
            "internship.start_date": self.internship_start_date,
            "internship.end_date": self.internship_end_date,
            "academic_year": self.academic_year,
            "current_year": self.current_year,
        }


AVAILABLE_VARIABLES: list[dict[str, str]] = [
    {"key": "organization.name", "label": "Название организации"},
    {"key": "student.full_name", "label": "ФИО студента"},
    {"key": "student.group", "label": "Группа студента"},
    {"key": "student.specialty", "label": "Специальность студента"},
    {"key": "student.department", "label": "Кафедра студента"},
    {"key": "teacher.full_name", "label": "ФИО преподавателя"},
    {"key": "internship.title", "label": "Название практики"},
    {"key": "internship.start_date", "label": "Дата начала практики"},
    {"key": "internship.end_date", "label": "Дата окончания практики"},
    {"key": "academic_year", "label": "Учебный год"},
    {"key": "current_year", "label": "Текущий год"},
]


def resolve_document(document: DocumentModel, context: VariableContext) -> DocumentModel:
    resolved = document.model_copy(deep=True)
    values = context.as_dict()

    def resolve_blocks(blocks: list[Block]) -> None:
        for block in blocks:
            if isinstance(block, (ParagraphBlock, HeadingBlock)):
                for run in block.runs:
                    if isinstance(run, VariableRun):
                        run.resolved_text = values.get(run.key, "{{" + run.key + "}}")
            elif isinstance(block, TableBlock):
                for row in block.rows:
                    for cell in row.cells:
                        resolve_blocks(cell.blocks)
            elif isinstance(block, ListBlock):
                for item in block.items:
                    resolve_blocks(item.blocks)

    for section in resolved.sections:
        resolve_blocks(section.blocks)
    if resolved.title_page:
        resolve_blocks(resolved.title_page.blocks)
    resolve_blocks(resolved.header.blocks)
    resolve_blocks(resolved.footer.blocks)

    return resolved
