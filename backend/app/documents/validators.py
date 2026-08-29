"""Structural document validation (rule 32). Pydantic already guarantees
type-correctness on parse (a malformed node simply fails to deserialize);
this module checks the business-rules Pydantic can't express: no duplicate
node ids (required for comment anchors to stay unambiguous, rule 38), no
unknown variable keys, sane page/typography values, no duplicate section
identity.
"""
from app.documents.schemas import Block, DocumentModel, HeadingBlock, ListBlock, ParagraphBlock, TableBlock, VariableRun
from app.documents.variables import AVAILABLE_VARIABLES

_KNOWN_VARIABLE_KEYS = {v["key"] for v in AVAILABLE_VARIABLES}


def validate_document(document: DocumentModel) -> list[str]:
    errors: list[str] = []
    seen_ids: set[str] = set()

    def check_id(node_id: str, where: str) -> None:
        if node_id in seen_ids:
            errors.append(f"Дублирующийся идентификатор узла «{node_id}» ({where}).")
        seen_ids.add(node_id)

    def walk_blocks(blocks: list[Block], where: str) -> None:
        for block in blocks:
            check_id(block.id, where)
            if isinstance(block, (ParagraphBlock, HeadingBlock)):
                for run in block.runs:
                    check_id(run.id, where)
                    if isinstance(run, VariableRun) and run.key not in _KNOWN_VARIABLE_KEYS:
                        errors.append(f"Неизвестная переменная «{{{{{run.key}}}}}» ({where}).")
                if isinstance(block, HeadingBlock) and not (1 <= block.level <= 3):
                    errors.append(f"Недопустимый уровень заголовка ({where}).")
            elif isinstance(block, TableBlock):
                if not block.rows:
                    errors.append(f"Таблица без строк ({where}).")
                for row in block.rows:
                    check_id(row.id, where)
                    for cell in row.cells:
                        check_id(cell.id, where)
                        walk_blocks(cell.blocks, where)
            elif isinstance(block, ListBlock):
                for item in block.items:
                    check_id(item.id, where)
                    walk_blocks(item.blocks, where)

    seen_section_ids: set[str] = set()
    seen_section_keys: set[str] = set()
    for section in document.sections:
        if section.id in seen_section_ids:
            errors.append(f"Дублирующийся идентификатор раздела «{section.id}».")
        seen_section_ids.add(section.id)
        if section.key:
            if section.key in seen_section_keys:
                errors.append(f"Дублирующийся ключ раздела «{section.key}».")
            seen_section_keys.add(section.key)
        walk_blocks(section.blocks, f"раздел «{section.title or section.key}»")

    if document.title_page:
        walk_blocks(document.title_page.blocks, "титульный лист")
    walk_blocks(document.header.blocks, "верхний колонтитул")
    walk_blocks(document.footer.blocks, "нижний колонтитул")

    if document.meta.margins.top_mm < 0 or document.meta.margins.bottom_mm < 0:
        errors.append("Верхнее/нижнее поле не может быть отрицательным.")
    if document.meta.margins.left_mm < 0 or document.meta.margins.right_mm < 0:
        errors.append("Левое/правое поле не может быть отрицательным.")
    if document.meta.default_font_size <= 0:
        errors.append("Размер шрифта должен быть положительным числом.")
    if document.meta.line_spacing <= 0:
        errors.append("Межстрочный интервал должен быть положительным числом.")

    return errors


def required_sections_present(original: DocumentModel, candidate: DocumentModel) -> list[str]:
    """Rule 14: a required section defined in the template must still be
    present by id in the candidate document — used when checking a report
    document against the template version it was created from."""
    errors: list[str] = []
    required_ids = {s.id for s in original.sections if s.required}
    candidate_ids = {s.id for s in candidate.sections}
    missing = required_ids - candidate_ids
    for section_id in missing:
        section = original.find_section(section_id)
        title = section.title if section else section_id
        errors.append(f"Обязательный раздел «{title}» отсутствует.")
    return errors
