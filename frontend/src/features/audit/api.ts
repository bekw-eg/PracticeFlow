import { api } from "../../lib/api";
import { DEFAULT_PAGE_SIZE, paginationFromResponse, type Paginated } from "../../lib/pagination";

export type AuditAction =
  | "MEMBERSHIP_CREATED" | "MEMBERSHIP_ROLE_CHANGED" | "MEMBERSHIP_ACTIVATED" | "MEMBERSHIP_DEACTIVATED"
  | "REPORT_SUBMITTED" | "REPORT_RESUBMITTED" | "REVIEW_STARTED" | "REPORT_APPROVED"
  | "REPORT_REVISION_REQUESTED" | "EXPORT_REQUESTED" | "EXPORT_DOWNLOADED" | "MFA_ENROLLED"
  | "MFA_RESET" | "AUDIT_LOG_VIEWED";

export interface AuditEvent {
  id: string;
  timestamp: string;
  action: string;
  actor_user_id: string | null;
  target_type: string | null;
  target_id: string | null;
  metadata: Record<string, unknown> | null;
  request_id_hash: string | null;
  correlation_id_hash: string | null;
  sequence: number | null;
  event_hash: string | null;
}

export interface AuditFilters {
  offset: number;
  action?: string;
  from?: string;
  to?: string;
  actor_id?: string;
  target_type?: string;
  target_id?: string;
}

export interface AuditIntegrity {
  valid: boolean;
  checked_events: number;
  first_invalid_sequence: number | null;
  retention_anchor_sequence: number;
}

export async function fetchAuditEvents(filters: AuditFilters): Promise<Paginated<AuditEvent>> {
  const params = new URLSearchParams({ offset: String(filters.offset), limit: String(DEFAULT_PAGE_SIZE) });
  const optional = {
    action: filters.action, from: filters.from, to: filters.to, actor_id: filters.actor_id,
    target_type: filters.target_type, target_id: filters.target_id,
  };
  for (const [key, value] of Object.entries(optional)) {
    if (value?.trim()) params.set(key, value.trim());
  }
  const response = await api.get<AuditEvent[]>(`/audit-events?${params.toString()}`);
  return { items: response.data, ...paginationFromResponse(response, { offset: filters.offset, limit: DEFAULT_PAGE_SIZE }, response.data.length) };
}

export async function verifyAuditIntegrity(): Promise<AuditIntegrity> {
  return (await api.get<AuditIntegrity>("/audit-events/integrity")).data;
}
