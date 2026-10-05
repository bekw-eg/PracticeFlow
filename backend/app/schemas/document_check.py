from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.schemas.review_group import TeacherReviewOut, WorkType

from app.models.enums import (
    CheckProfileVersionStatus,
    CheckRuleSeverity,
    CheckRuleType,
    DocumentCheckAssignmentStatus,
    DocumentCheckJobStatus,
)


class StrictRuleConfig(BaseModel):
    """Base for persisted rule JSON.

    Unknown keys and coercion are rejected so a misspelled setting cannot be
    stored while appearing to be active.
    """

    model_config = ConfigDict(extra="forbid", strict=True)


class PageMargins(StrictRuleConfig):
    top_mm: float = Field(ge=0, le=100)
    right_mm: float = Field(ge=0, le=100)
    bottom_mm: float = Field(ge=0, le=100)
    left_mm: float = Field(ge=0, le=100)


class PageFormatMarginsConfig(StrictRuleConfig):
    page_size: Literal["A4", "LETTER", "LEGAL", "CUSTOM"] = "A4"
    orientation: Literal["PORTRAIT", "LANDSCAPE"] = "PORTRAIT"
    margins: PageMargins
    width_mm: float | None = Field(default=None, gt=0, le=1000)
    height_mm: float | None = Field(default=None, gt=0, le=1000)

    @model_validator(mode="after")
    def custom_size_has_dimensions(self):
        if self.page_size == "CUSTOM" and (self.width_mm is None or self.height_mm is None):
            raise ValueError("CUSTOM page size requires width_mm and height_mm")
        if self.page_size != "CUSTOM" and (self.width_mm is not None or self.height_mm is not None):
            raise ValueError("width_mm and height_mm are only valid for CUSTOM page size")
        return self


class FontsSizesConfig(StrictRuleConfig):
    allowed_fonts: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]] = Field(
        min_length=1, max_length=20
    )
    min_size_pt: float = Field(gt=0, le=200)
    max_size_pt: float = Field(gt=0, le=200)

    @model_validator(mode="after")
    def size_range_is_ordered(self):
        if self.max_size_pt < self.min_size_pt:
            raise ValueError("max_size_pt must be greater than or equal to min_size_pt")
        if len({font.casefold() for font in self.allowed_fonts}) != len(self.allowed_fonts):
            raise ValueError("allowed_fonts must not contain duplicates")
        return self


class ParagraphSpacingIndentsConfig(StrictRuleConfig):
    line_spacing: float = Field(gt=0, le=10)
    space_before_pt: float = Field(ge=0, le=200)
    space_after_pt: float = Field(ge=0, le=200)
    first_line_indent_mm: float = Field(ge=-100, le=100)
    left_indent_mm: float = Field(ge=0, le=100)
    right_indent_mm: float = Field(ge=0, le=100)
    alignment: Literal["LEFT", "CENTER", "RIGHT", "JUSTIFY"] | None = None


class HeadingLevelConfig(StrictRuleConfig):
    level: int = Field(ge=1, le=6)
    min_size_pt: float = Field(gt=0, le=200)
    max_size_pt: float = Field(gt=0, le=200)
    bold: bool | None = None
    alignment: Literal["LEFT", "CENTER", "RIGHT", "JUSTIFY"] | None = None
    allowed_fonts: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]] | None = Field(default=None, min_length=1, max_length=20)
    line_spacing: float | None = Field(default=None, gt=0, le=10)
    space_before_pt: float | None = Field(default=None, ge=0, le=200)
    space_after_pt: float | None = Field(default=None, ge=0, le=200)
    first_line_indent_mm: float | None = Field(default=None, ge=-100, le=100)
    left_indent_mm: float | None = Field(default=None, ge=0, le=100)
    right_indent_mm: float | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def size_range_is_ordered(self):
        if self.max_size_pt < self.min_size_pt:
            raise ValueError("max_size_pt must be greater than or equal to min_size_pt")
        return self


class HeadingsConfig(StrictRuleConfig):
    levels: list[HeadingLevelConfig] = Field(min_length=1, max_length=6)
    require_numbering: bool = False

    @model_validator(mode="after")
    def levels_are_unique(self):
        values = [level.level for level in self.levels]
        if len(set(values)) != len(values):
            raise ValueError("heading levels must be unique")
        return self


class TablesConfig(StrictRuleConfig):
    require_header_row: bool = True
    require_caption: bool = False
    caption_position: Literal["ABOVE", "BELOW"] = "ABOVE"
    allowed_alignments: list[Literal["LEFT", "CENTER", "RIGHT"]] = Field(min_length=1, max_length=3)


class FigureCaptionsConfig(StrictRuleConfig):
    required: bool = True
    position: Literal["ABOVE", "BELOW"] = "BELOW"
    numbering: Literal["ARABIC", "ROMAN", "NONE"] = "ARABIC"
    prefix: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)] = "Figure"


class ReferencesConfig(StrictRuleConfig):
    style: Literal["APA", "MLA", "CHICAGO", "GOST", "IEEE", "CUSTOM"]
    minimum_count: int = Field(ge=0, le=10000)
    require_in_text_citations: bool = True
    custom_style_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)] | None = None

    @model_validator(mode="after")
    def custom_style_is_named(self):
        if self.style == "CUSTOM" and self.custom_style_name is None:
            raise ValueError("CUSTOM reference style requires custom_style_name")
        if self.style != "CUSTOM" and self.custom_style_name is not None:
            raise ValueError("custom_style_name is only valid for CUSTOM reference style")
        return self


class RequiredSectionsConfig(StrictRuleConfig):
    sections: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]] = Field(
        min_length=1, max_length=100
    )
    case_sensitive: bool = False

    @model_validator(mode="after")
    def sections_are_unique(self):
        values = self.sections if self.case_sensitive else [value.casefold() for value in self.sections]
        if len(set(values)) != len(values):
            raise ValueError("sections must not contain duplicates")
        return self


LanguageTag = Annotated[
    str,
    StringConstraints(strip_whitespace=True, pattern=r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$", max_length=35),
]


def _registered_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("assignment_timezone must be a registered IANA timezone name") from exc
    return value


AssignmentTimezone = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        pattern=r"^(?:UTC|[A-Za-z][A-Za-z0-9_+\-]*(?:/[A-Za-z0-9_+\-]+)+)$",
        max_length=64,
    ),
    AfterValidator(_registered_timezone),
]


class SpellingLanguagesConfig(StrictRuleConfig):
    languages: list[LanguageTag] = Field(min_length=1, max_length=20)
    ignore_uppercase: bool = True
    ignore_urls: bool = True

    @model_validator(mode="after")
    def languages_are_unique(self):
        if len({language.casefold() for language in self.languages}) != len(self.languages):
            raise ValueError("languages must not contain duplicates")
        return self


RuleConfig = (
    PageFormatMarginsConfig
    | FontsSizesConfig
    | ParagraphSpacingIndentsConfig
    | HeadingsConfig
    | TablesConfig
    | FigureCaptionsConfig
    | ReferencesConfig
    | RequiredSectionsConfig
    | SpellingLanguagesConfig
)

RULE_CONFIG_MODELS: dict[CheckRuleType, type[StrictRuleConfig]] = {
    CheckRuleType.PAGE_FORMAT_MARGINS: PageFormatMarginsConfig,
    CheckRuleType.FONTS_SIZES: FontsSizesConfig,
    CheckRuleType.PARAGRAPH_SPACING_INDENTS: ParagraphSpacingIndentsConfig,
    CheckRuleType.HEADINGS: HeadingsConfig,
    CheckRuleType.TABLES: TablesConfig,
    CheckRuleType.FIGURE_CAPTIONS: FigureCaptionsConfig,
    CheckRuleType.REFERENCES: ReferencesConfig,
    CheckRuleType.REQUIRED_SECTIONS: RequiredSectionsConfig,
    CheckRuleType.SPELLING_LANGUAGES: SpellingLanguagesConfig,
}


def validate_rule_config(rule_type: CheckRuleType | str, schema_version: int, config: Any) -> dict:
    if schema_version != 1:
        raise ValueError("Only rule config schema version 1 is supported")
    normalized_type = CheckRuleType(rule_type)
    model = RULE_CONFIG_MODELS[normalized_type]
    if isinstance(config, BaseModel):
        config = config.model_dump(mode="json")
    return model.model_validate(config).model_dump(mode="json")


class CheckRuleWrite(BaseModel):
    rule_type: CheckRuleType
    category: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    severity: CheckRuleSeverity
    enabled: bool = True
    sort_order: int = Field(ge=0)
    config_schema_version: int = 1
    config: dict[str, Any]

    @model_validator(mode="after")
    def config_matches_rule_type(self):
        self.config = validate_rule_config(self.rule_type, self.config_schema_version, self.config)
        return self


class BulkReplaceCheckRulesRequest(BaseModel):
    rules: list[CheckRuleWrite] = Field(max_length=200)

    @model_validator(mode="after")
    def sort_orders_are_unique(self):
        orders = [rule.sort_order for rule in self.rules]
        if len(set(orders)) != len(orders):
            raise ValueError("sort_order must be unique within a profile version")
        return self


class CheckRuleOut(BaseModel):
    id: uuid.UUID
    rule_type: CheckRuleType
    category: str
    severity: CheckRuleSeverity
    enabled: bool
    sort_order: int
    config_schema_version: int
    config: dict[str, Any]

    model_config = ConfigDict(from_attributes=True)


class CheckProfileVersionSummary(BaseModel):
    id: uuid.UUID
    profile_id: uuid.UUID
    version_number: int
    state: CheckProfileVersionStatus
    notes: str | None
    published_at: datetime | None
    retired_at: datetime | None
    created_at: datetime
    executable_rule_count: int

    model_config = ConfigDict(from_attributes=True)


class CheckProfileVersionDetail(CheckProfileVersionSummary):
    rules: list[CheckRuleOut]


class CheckProfileOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime
    versions: list[CheckProfileVersionSummary] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class CreateCheckProfileRequest(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=5000)] | None = None


class UpdateCheckProfileRequest(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)] | None = None
    description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=5000)] | None = None


class CreateCheckProfileVersionRequest(BaseModel):
    notes: Annotated[str, StringConstraints(strip_whitespace=True, max_length=5000)] | None = None
    source_version_id: uuid.UUID | None = None


class UpdateCheckProfileVersionRequest(BaseModel):
    notes: Annotated[str, StringConstraints(strip_whitespace=True, max_length=5000)] | None = None


class AssignmentStudentOut(BaseModel):
    id: uuid.UUID
    student_id: uuid.UUID
    full_name: str
    email: str


class DocumentCheckAssignmentSummary(BaseModel):
    id: uuid.UUID
    group_id: uuid.UUID
    profile_version_id: uuid.UUID
    title: str
    instructions: str | None
    state: DocumentCheckAssignmentStatus
    due_at: datetime
    assignment_timezone: str
    published_at: datetime | None
    closed_at: datetime | None
    created_at: datetime
    roster_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class DocumentCheckAssignmentDetail(DocumentCheckAssignmentSummary):
    students: list[AssignmentStudentOut]


class CreateDocumentCheckAssignmentRequest(BaseModel):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    instructions: Annotated[str, StringConstraints(strip_whitespace=True, max_length=10000)] | None = None
    profile_version_id: uuid.UUID
    due_at: AwareDatetime
    assignment_timezone: AssignmentTimezone


class UpdateDocumentCheckAssignmentRequest(BaseModel):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)] | None = None
    instructions: Annotated[str, StringConstraints(strip_whitespace=True, max_length=10000)] | None = None
    profile_version_id: uuid.UUID | None = None
    due_at: AwareDatetime | None = None
    assignment_timezone: AssignmentTimezone | None = None


class StudentDocumentCheckAssignmentDetail(DocumentCheckAssignmentSummary):
    assignment_student_id: uuid.UUID


class DocumentCheckResultSummaryOut(BaseModel):
    analyzer_version: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    rules_total: int = Field(ge=0)
    rules_evaluated: int = Field(ge=0)
    rules_skipped: int = Field(ge=0)
    findings_count: int = Field(ge=0, le=50000)
    findings_truncated: bool
    first_page_exclusion: Literal["APPLIED", "BOUNDARY_UNKNOWN", "NO_CONTENT"] | None = None

    @model_validator(mode="after")
    def validate_counts(self) -> DocumentCheckResultSummaryOut:
        if self.rules_total != self.rules_evaluated + self.rules_skipped:
            raise ValueError("rules_total must equal evaluated plus skipped rules")
        return self

    model_config = ConfigDict(extra="forbid")


class DocumentCheckJobOut(BaseModel):
    id: uuid.UUID
    status: DocumentCheckJobStatus
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error_code: str | None
    error_message: str | None
    analyzer_version: str | None
    attempt_count: int
    result_summary: DocumentCheckResultSummaryOut | None
    run_number: int = 1
    settings_revision: int | None = None

    model_config = ConfigDict(from_attributes=True)


class StudentDocumentSubmissionOut(BaseModel):
    id: uuid.UUID
    assignment_id: uuid.UUID
    assignment_student_id: uuid.UUID
    student_id: uuid.UUID
    attempt_number: int
    original_filename: str
    size_bytes: int
    sha256: str
    detected_mime: str
    submitted_at: datetime
    is_late: bool
    preflight_schema_version: int
    created_at: datetime
    job: DocumentCheckJobOut

    model_config = ConfigDict(from_attributes=True)


class DocumentLifecycleWrite(BaseModel):
    revision: int = Field(ge=0)
    archived: bool
    disclosure_allowed: bool
    model_config = ConfigDict(extra="forbid")


class DocumentOriginalDelete(BaseModel):
    revision: int = Field(ge=0)
    model_config = ConfigDict(extra="forbid")


class DocumentLifecycleOut(DocumentLifecycleWrite):
    original_delete_requested_at: datetime | None
    original_deleted_at: datetime | None
    model_config = ConfigDict(from_attributes=True)



class TeacherDocumentSubmissionOut(BaseModel):
    id: uuid.UUID
    profile_version_id: uuid.UUID
    student_label: str | None
    review_group_id: uuid.UUID | None = None
    work_title: str | None = None
    work_type: WorkType | None = None
    teacher_review: TeacherReviewOut | None = None
    original_filename: str
    size_bytes: int
    sha256: str
    detected_mime: str
    submitted_at: datetime
    preflight_schema_version: int
    plagiarism_source_disclosure_allowed: bool
    created_at: datetime
    job: DocumentCheckJobOut
    latest_completed_job: DocumentCheckJobOut | None = None
    lifecycle: DocumentLifecycleOut | None = None

    model_config = ConfigDict(from_attributes=True)


class TeacherDocumentPreviewOut(BaseModel):
    html: str
    paragraph_count: int
    page_width_mm: float
    page_height_mm: float
    margin_top_mm: float
    margin_right_mm: float
    margin_bottom_mm: float
    margin_left_mm: float

    model_config = ConfigDict(from_attributes=True)


class DocumentCheckFindingOut(BaseModel):
    id: uuid.UUID
    check_rule_id: uuid.UUID | None
    run_rule_id: uuid.UUID | None = None
    sequence: int
    rule_type: CheckRuleType
    category: str
    severity: CheckRuleSeverity
    code: str
    property_name: str
    location: dict[str, Any]
    expected: dict[str, Any]
    actual: dict[str, Any]
    finding_schema_version: int

    model_config = ConfigDict(from_attributes=True)


ParagraphType = Literal["BODY", "HEADING_1", "HEADING_2", "HEADING_3", "HEADING_4", "HEADING_5", "HEADING_6"]
ParagraphIndex = Annotated[str, StringConstraints(pattern=r"^[1-9][0-9]{0,6}$")]


class DocumentSettingsWrite(BulkReplaceCheckRulesRequest):
    # A legacy profile can contain 200 rules; its document defaults can add HEADINGS.
    rules: list[CheckRuleWrite] = Field(max_length=201)
    revision: int = Field(ge=1)
    paragraph_overrides: dict[ParagraphIndex, ParagraphType] = Field(default_factory=dict, max_length=50000)
    model_config = ConfigDict(extra="forbid")


class DocumentSettingsOut(DocumentSettingsWrite):
    submission_id: uuid.UUID
    updated_at: datetime


class DocumentRecheckRequest(BaseModel):
    revision: int = Field(ge=1)
    model_config = ConfigDict(extra="forbid")


class ParagraphClassificationOut(BaseModel):
    paragraph_index: int
    automatic_type: ParagraphType
    paragraph_type: ParagraphType
    source: Literal["MANUAL", "STRUCTURE", "HEURISTIC", "BODY"]
    excluded: bool


class DocumentRunDetailOut(DocumentCheckJobOut):
    rules: list[CheckRuleWrite]
    paragraph_overrides: dict[str, ParagraphType]


class LocalPlagiarismRunOut(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    status: DocumentCheckJobStatus
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    algorithm_version: str
    minimum_match_words: int = Field(ge=3)
    target_word_count: int = Field(ge=0)
    excluded_word_count: int = Field(ge=0)
    matched_word_count: int = Field(ge=0)
    similarity_percent: float = Field(ge=0, le=100)
    candidate_documents_available: int = Field(ge=0)
    candidate_documents_scanned: int = Field(ge=0)
    matches_count: int = Field(ge=0)
    matches_truncated: bool
    error_code: str | None
    error_message: str | None

    model_config = ConfigDict(from_attributes=True)


class LocalPlagiarismMatchOut(BaseModel):
    id: uuid.UUID
    sequence: int = Field(ge=1)
    target_paragraph_index: int = Field(ge=1)
    source_paragraph_index: int | None = Field(default=None, ge=1)
    matched_word_count: int = Field(ge=1)
    target_excerpt: str
    source_excerpt: str | None = None
    source_submission_id: uuid.UUID | None = None
    source_label: str | None = None
    source_filename: str | None = None
    source_restricted: bool
