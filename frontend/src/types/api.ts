export type Role = "SUPER_ADMIN" | "DIRECTOR" | "TEACHER" | "STUDENT";

export interface CurrentUser {
  user_id: string;
  organization_id: string;
  full_name: string;
  email: string;
  role: Role;
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

export interface ReportOut {
  id: string;
  internship_id: string;
  student_id: string;
  status: ReportStatus;
  current_version_id: string | null;
  created_at: string;
}

export interface ReportVersionOut {
  id: string;
  version_number: number;
  submitted_at: string;
}

export interface ReportDetail extends ReportOut {
  versions: ReportVersionOut[];
  deadline: string;
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
