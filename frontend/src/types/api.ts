export type Role = "SUPER_ADMIN" | "DIRECTOR" | "TEACHER" | "STUDENT";

export interface ProductFeatures {
  document_check_enabled: boolean;
  legacy_document_editor_enabled: boolean;
}

export interface CurrentUser {
  user_id: string;
  organization_id: string;
  full_name: string;
  email: string;
  role: Role;
  features: ProductFeatures;
}

export interface GroupSummary {
  id: string;
  name: string;
  academic_year: string | null;
  student_count: number;
}

export interface GroupMemberOut {
  id: string;
  student_id: string;
  full_name: string;
  email: string;
}

export interface BulkStudentOperationFailure {
  student_id: string;
  code: "NOT_IN_SOURCE_GROUP" | "ALREADY_IN_TARGET_GROUP" | "TRANSFER_CONFLICT" | string;
}

export interface BulkStudentOperationResult {
  succeeded_student_ids: string[];
  failed: BulkStudentOperationFailure[];
}

export interface StudentOptionOut {
  id: string;
  full_name: string;
  email: string;
  specialty_name: string | null;
}

export interface GroupDetail {
  id: string;
  name: string;
  academic_year: string | null;
  students: GroupMemberOut[];
}

export type InternshipStatus = "DRAFT" | "PUBLISHED" | "CLOSED";

export interface InternshipOut {
  id: string;
  title: string;
  description: string | null;
  status: InternshipStatus;
  template_version_id: string;
  start_date: string;
  end_date: string;
  deadline: string;
  created_at: string;
}

export type ReportStatus = "DRAFT" | "SUBMITTED" | "UNDER_REVIEW" | "REVISION_REQUIRED" | "APPROVED" | "LOCKED";
export type ReportDeadlineState = "UPCOMING" | "DUE_SOON" | "DUE_TODAY" | "OVERDUE" | "SUBMITTED_ON_TIME" | "SUBMITTED_LATE";

export interface ReportOut {
  id: string;
  internship_id: string;
  student_id: string;
  status: ReportStatus;
  current_version_id: string | null;
  created_at: string;
}

export interface StudentReportOut extends ReportOut {
  internship_title: string;
  internship_description: string | null;
  group_name: string;
  start_date: string;
  end_date: string;
  deadline: string;
  deadline_state: ReportDeadlineState;
}

export type ReviewQueueDeadlineFilter = "overdue" | "due_today" | "due_soon" | "upcoming";

export interface TeacherReviewQueueItem extends ReportOut {
  student_name: string;
  internship_title: string;
  deadline: string;
  is_overdue: boolean;
  submitted_late: boolean;
  open_comments_count: number;
}

export interface ReportVersionOut {
  id: string;
  version_number: number;
  submitted_at: string;
}

export interface ReportDetail extends ReportOut {
  versions: ReportVersionOut[];
  deadline: string;
  internship_title: string;
}

export interface TemplateVersionSummary {
  id: string;
  version_number: number;
  is_published: boolean;
  is_locked: boolean;
  created_at: string;
}

export interface TemplateOut {
  id: string;
  name: string;
  description: string | null;
  versions: TemplateVersionSummary[];
}

export interface CommentAuthor {
  id: string;
  full_name: string;
}

export interface CommentReply {
  id: string;
  author: CommentAuthor;
  body: string;
  created_at: string;
}

export interface ReportComment {
  id: string;
  report_version_id: string;
  author: CommentAuthor;
  is_general: boolean;
  node_id: string | null;
  start_offset: number | null;
  end_offset: number | null;
  text_snapshot: string | null;
  body: string;
  status: "OPEN" | "RESOLVED";
  anchor_status: "valid" | "invalid" | null;
  current_node_text: string | null;
  created_at: string;
  resolved_at: string | null;
  replies: CommentReply[];
}

export interface ReportHistoryEntry {
  event: string;
  actor_name: string | null;
  actor_role: string | null;
  created_at: string;
  metadata: Record<string, unknown> | null;
}

export interface StudentProfile {
  student_id: string;
  full_name: string;
  email: string;
  specialty_name: string | null;
  groups: { id: string; name: string; academic_year: string | null }[];
  reports_count: number;
}

export interface OrganizationOut {
  id: string;
  name: string;
  slug: string;
}

export interface ManagementOverview {
  organization: OrganizationOut;
  members_count: number;
  students_count: number;
  teachers_count: number;
  groups_count: number;
  active_reports_count: number;
}

export type CheckProfileVersionStatus = "DRAFT" | "PUBLISHED" | "RETIRED";
export type CheckRuleType = "PAGE_FORMAT_MARGINS" | "FONTS_SIZES" | "PARAGRAPH_SPACING_INDENTS" | "HEADINGS" | "TABLES" | "FIGURE_CAPTIONS" | "REFERENCES" | "REQUIRED_SECTIONS" | "SPELLING_LANGUAGES";
export type CheckRuleSeverity = "INFO" | "WARNING" | "ERROR";

export interface CheckRule {
  id?: string;
  rule_type: CheckRuleType;
  category: string;
  severity: CheckRuleSeverity;
  enabled: boolean;
  sort_order: number;
  config_schema_version: 1;
  config: Record<string, unknown>;
}

export interface CheckProfileVersion {
  id: string;
  profile_id: string;
  version_number: number;
  state: CheckProfileVersionStatus;
  notes: string | null;
  published_at: string | null;
  retired_at: string | null;
  created_at: string;
  executable_rule_count: number;
  rules?: CheckRule[];
}

export interface CheckProfile {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  versions: CheckProfileVersion[];
}

export type DocumentCheckJobStatus = "QUEUED" | "PROCESSING" | "COMPLETED" | "FAILED";

export interface DocumentCheckJob {
  id: string;
  status: DocumentCheckJobStatus;
  queued_at: string;
  started_at: string | null;
  finished_at: string | null;
  error_code: string | null;
  error_message: string | null;
  analyzer_version: string | null;
  attempt_count: number;
  result_summary: DocumentCheckResultSummary | null;
  run_number?: number;
  settings_revision?: number | null;
}

export interface DocumentCheckResultSummary {
  analyzer_version: string;
  rules_total: number;
  rules_evaluated: number;
  rules_skipped: number;
  findings_count: number;
  findings_truncated: boolean;
  first_page_exclusion?: "APPLIED" | "BOUNDARY_UNKNOWN" | "NO_CONTENT" | null;
}

export interface DocumentCheckFinding {
  id: string;
  check_rule_id: string | null;
  run_rule_id?: string | null;
  sequence: number;
  rule_type: CheckRuleType;
  category: string;
  severity: CheckRuleSeverity;
  code: string;
  property_name: string;
  location: Record<string, unknown>;
  expected: Record<string, unknown>;
  actual: Record<string, unknown>;
  finding_schema_version: number;
}

export interface TeacherReview {
  revision: number;
  remarks: string;
  completed_at: string | null;
  completed_by_teacher_id: string | null;
  completed_job_id: string | null;
}

export interface TeacherDocumentSubmission {
  review_group_id?: string | null;
  work_title?: string | null;
  work_type?: "COURSEWORK" | "REPORT" | null;
  teacher_review?: TeacherReview | null;
  id: string;
  profile_version_id: string;
  student_label: string | null;
  original_filename: string;
  size_bytes: number;
  sha256: string;
  detected_mime: string;
  submitted_at: string;
  preflight_schema_version: number;
  plagiarism_source_disclosure_allowed: boolean;
  created_at: string;
  job: DocumentCheckJob;
  latest_completed_job?: DocumentCheckJob | null;
  lifecycle?: DocumentLifecycle | null;
}

export interface DocumentLifecycle {
  revision: number;
  archived: boolean;
  disclosure_allowed: boolean;
  original_delete_requested_at: string | null;
  original_deleted_at: string | null;
}

export type ParagraphType = "BODY" | "HEADING_1" | "HEADING_2" | "HEADING_3" | "HEADING_4" | "HEADING_5" | "HEADING_6";

export interface DocumentSettings {
  submission_id: string;
  revision: number;
  rules: CheckRule[];
  paragraph_overrides: Record<string, ParagraphType>;
  updated_at: string;
}

export interface ParagraphClassification {
  paragraph_index: number;
  automatic_type: ParagraphType;
  paragraph_type: ParagraphType;
  source: "MANUAL" | "STRUCTURE" | "HEURISTIC" | "BODY";
  excluded: boolean;
}

export interface DocumentRunDetail extends DocumentCheckJob {
  rules: CheckRule[];
  paragraph_overrides: Record<string, ParagraphType>;
}

export interface LocalPlagiarismRun {
  id: string;
  job_id: string;
  status: DocumentCheckJobStatus;
  queued_at: string;
  started_at: string | null;
  finished_at: string | null;
  algorithm_version: string;
  minimum_match_words: number;
  target_word_count: number;
  excluded_word_count: number;
  matched_word_count: number;
  similarity_percent: number;
  candidate_documents_available: number;
  candidate_documents_scanned: number;
  matches_count: number;
  matches_truncated: boolean;
  error_code: string | null;
  error_message: string | null;
}

export interface LocalPlagiarismMatch {
  id: string;
  sequence: number;
  target_paragraph_index: number;
  source_paragraph_index: number | null;
  matched_word_count: number;
  target_excerpt: string;
  source_excerpt: string | null;
  source_submission_id: string | null;
  source_label: string | null;
  source_filename: string | null;
  source_restricted: boolean;
}

export interface TeacherDocumentPreview {
  html: string;
  paragraph_count: number;
  page_width_mm: number;
  page_height_mm: number;
  margin_top_mm: number;
  margin_right_mm: number;
  margin_bottom_mm: number;
  margin_left_mm: number;
}

export interface DirectorReportStatusCount {
  status: ReportStatus;
  count: number;
}

export interface DirectorGroupSummary {
  id: string;
  name: string;
  academic_year: string | null;
  student_count: number;
  internships_count: number;
  reports_count: number;
  overdue_reports_count: number;
}

export interface DirectorInternshipSummary {
  id: string;
  title: string;
  group_id: string;
  group_name: string;
  status: InternshipStatus;
  start_date: string;
  end_date: string;
  deadline: string;
  reports_count: number;
  overdue_reports_count: number;
}

export interface DirectorTeacherLoad {
  id: string;
  full_name: string;
  groups_count: number;
  active_internships_count: number;
  reports_to_review_count: number;
}

export interface DirectorDashboard {
  organization: OrganizationOut;
  groups_count: number;
  internships_count: number;
  active_internships_count: number;
  reports_count: number;
  overdue_reports_count: number;
  report_statuses: DirectorReportStatusCount[];
  groups: DirectorGroupSummary[];
  internships: DirectorInternshipSummary[];
  teacher_loads: DirectorTeacherLoad[];
}

export interface DepartmentOut {
  id: string;
  name: string;
}

export interface SpecialtyOut {
  id: string;
  name: string;
  code: string | null;
  department_id: string;
}

export interface ManagementMember {
  id: string;
  user_id: string;
  full_name: string;
  email: string;
  role: Role;
  profile_id: string | null;
  department_id: string | null;
  specialty_id: string | null;
  group_names: string[];
  is_active: boolean;
}

export interface ManagementGroup {
  id: string;
  name: string;
  academic_year: string | null;
  specialty_id: string | null;
  student_count: number;
  teacher_ids: string[];
  teacher_names: string[];
}

export interface ManagementCatalog {
  departments: DepartmentOut[];
  specialties: SpecialtyOut[];
}

export interface NotificationOut {
  id: string;
  type: string;
  title: string;
  body: string | null;
  link: string | null;
  read_at: string | null;
  created_at: string;
}

export interface OrganizationChoice {
  id: string;
  name: string;
  slug: string;
  role: Role;
}

export interface GroupReportProgress {
  total: number;
  draft: number;
  submitted: number;
  under_review: number;
  revision_required: number;
  locked: number;
}
