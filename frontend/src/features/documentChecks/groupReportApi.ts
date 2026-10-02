import type { CheckRuleType } from "../../types/api";
import type { GroupSummary } from "./reviewGroupApi";

export interface ReportFinding { id: string; rule_type: CheckRuleType; location: Record<string, number>; actual: Record<string, unknown>; expected: Record<string, unknown> }
export interface ReportContent {
  title: string; introduction: string; conclusions: string; selected_rule_types: CheckRuleType[]; finding_ids: string[];
  remark_submission_ids: string[]; examples: ReportFinding[]; remarks: string[];
}
export interface GroupReport {
  id: string; group_id: string; locale: string; revision: number; created_at: string; generated_at: string | null;
  content: ReportContent;
  snapshot: { group_name: string; captured_at: string; summary: GroupSummary; skipped_works: number;
    remarks: { submission_id: string; text: string }[] };
}
export type GroupReportItem = Pick<GroupReport, "id" | "locale" | "revision" | "created_at" | "generated_at"> & { title: string };
export const reportBase = (groupId: string) => `/document-checks/teacher/groups/${groupId}/reports`;

export function reportPayload(report: GroupReport, content: ReportContent) {
  const { title, introduction, conclusions, selected_rule_types, finding_ids, remark_submission_ids } = content;
  return { revision: report.revision, title, introduction, conclusions, selected_rule_types, finding_ids, remark_submission_ids };
}
