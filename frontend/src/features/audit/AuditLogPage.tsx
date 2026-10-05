import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";

import { ErrorState, EmptyState, LoadingState } from "../../components/ui/StateViews";
import { PaginationControls } from "../../components/ui/PaginationControls";
import { fetchAuditEvents, verifyAuditIntegrity, type AuditFilters } from "./api";
import { useTranslation } from "react-i18next";
import { useLocaleFormatters } from "../../i18n/formatters";

const actions = ["", "MEMBERSHIP_CREATED", "MEMBERSHIP_ROLE_CHANGED", "MEMBERSHIP_DEACTIVATED", "REPORT_SUBMITTED", "REPORT_APPROVED", "REPORT_REVISION_REQUESTED", "EXPORT_REQUESTED", "EXPORT_DOWNLOADED", "MFA_ENROLLED", "MFA_RESET"];
const ACTION_TRANSLATION_KEYS = {
  MEMBERSHIP_CREATED: "actions.MEMBERSHIP_CREATED", MEMBERSHIP_ROLE_CHANGED: "actions.MEMBERSHIP_ROLE_CHANGED", MEMBERSHIP_DEACTIVATED: "actions.MEMBERSHIP_DEACTIVATED", REPORT_SUBMITTED: "actions.REPORT_SUBMITTED", REPORT_APPROVED: "actions.REPORT_APPROVED", REPORT_REVISION_REQUESTED: "actions.REPORT_REVISION_REQUESTED", EXPORT_REQUESTED: "actions.EXPORT_REQUESTED", EXPORT_DOWNLOADED: "actions.EXPORT_DOWNLOADED", MFA_ENROLLED: "actions.MFA_ENROLLED", MFA_RESET: "actions.MFA_RESET",
} as const;

function compactId(value: string | null) {
  return value ? `${value.slice(0, 8)}…${value.slice(-4)}` : "—";
}

function details(event: { metadata: Record<string, unknown> | null; sequence: number | null }) {
  const metadata = event.metadata ? Object.entries(event.metadata).map(([key, value]) => `${key}: ${String(value)}`).join(" · ") : "";
  return [event.sequence ? `#${event.sequence}` : "", metadata].filter(Boolean).join(" · ") || "—";
}

export function AuditLogPage() {
  const { t } = useTranslation("audit");
  const { formatCount, formatDateTime } = useLocaleFormatters();
  const [filters, setFilters] = useState<AuditFilters>({ offset: 0 });
  const query = useQuery({ queryKey: ["audit-events", filters], queryFn: () => fetchAuditEvents(filters) });
  const integrity = useMutation({ mutationFn: verifyAuditIntegrity });
  const change = (key: Exclude<keyof AuditFilters, "offset">, value: string) => setFilters((current) => ({ ...current, offset: 0, [key]: value || undefined }));

  if (query.isLoading) return <LoadingState label={t("loadingAuditLog")} />;
  if (query.isError) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  const page = query.data;
  if (!page) return <ErrorState message={t("auditUnavailable")} onRetry={() => void query.refetch()} />;

  const actionLabel = (action: string) => action ? t(ACTION_TRANSLATION_KEYS[action as keyof typeof ACTION_TRANSLATION_KEYS] ?? "unknownAction") : t("allActions");
  return <section className="space-y-5">
    <header className="card p-6"><div className="flex flex-wrap items-start justify-between gap-4"><div><h1 className="font-display text-2xl font-extrabold text-[var(--color-ink)]">{t("auditLog")}</h1><p className="mt-1 max-w-3xl text-sm leading-6 text-[var(--color-muted)]">{t("auditDescription")}</p></div><button type="button" className="btn btn-secondary" disabled={integrity.isPending} onClick={() => integrity.mutate()}>{t("verifyIntegrity")}</button></div>{integrity.data && <p className={`mt-4 rounded-xl px-4 py-3 text-sm ${integrity.data.valid ? "bg-emerald-50 text-emerald-800" : "bg-[var(--color-danger-50)] text-[var(--color-danger-500)]"}`} role="status">{integrity.data.valid ? formatCount(integrity.data.checked_events, (values) => t("integrityValid", values)) : t("integrityInvalid", { sequence: integrity.data.first_invalid_sequence ?? t("unknownValue") })}</p>}{integrity.isError && <p className="mt-4 text-sm text-[var(--color-danger-500)]" role="alert">{t("integrityError")}</p>}</header>
    <div className="card p-5"><div className="grid gap-3 md:grid-cols-3"><label><span className="form-label">{t("action")}</span><select aria-label={t("actionFilter")} className="input" value={filters.action ?? ""} onChange={(event) => change("action", event.target.value)}>{actions.map((action) => <option key={action} value={action}>{actionLabel(action)}</option>)}</select></label><label><span className="form-label">{t("from")}</span><input aria-label={t("fromFilter")} type="datetime-local" className="input" value={filters.from ?? ""} onChange={(event) => change("from", event.target.value ? new Date(event.target.value).toISOString() : "")} /></label><label><span className="form-label">{t("to")}</span><input aria-label={t("toFilter")} type="datetime-local" className="input" value={filters.to ?? ""} onChange={(event) => change("to", event.target.value ? new Date(event.target.value).toISOString() : "")} /></label><label><span className="form-label">{t("actorId")}</span><input aria-label={t("actorId")} className="input" value={filters.actor_id ?? ""} onChange={(event) => change("actor_id", event.target.value)} /></label><label><span className="form-label">{t("targetType")}</span><input aria-label={t("targetType")} className="input" value={filters.target_type ?? ""} onChange={(event) => change("target_type", event.target.value)} /></label><label><span className="form-label">{t("targetId")}</span><input aria-label={t("targetId")} className="input" value={filters.target_id ?? ""} onChange={(event) => change("target_id", event.target.value)} /></label></div></div>
    {page.items.length === 0 ? <EmptyState title={t("noEvents")} description={t("noEventsDescription")} /> : <div className="card overflow-x-auto"><table className="table-base min-w-[840px]"><thead><tr><th className="px-5 py-3">{t("time")}</th><th className="px-5 py-3">{t("action")}</th><th className="px-5 py-3">{t("actor")}</th><th className="px-5 py-3">{t("target")}</th><th className="px-5 py-3">{t("safeDetails")}</th></tr></thead><tbody>{page.items.map((event) => <tr key={event.id}><td className="whitespace-nowrap px-5 py-3 text-sm text-[var(--color-muted)]">{formatDateTime(event.timestamp)}</td><td className="px-5 py-3 text-xs text-[var(--color-ink)]">{actionLabel(event.action)}</td><td className="px-5 py-3 font-mono-code text-xs text-[var(--color-muted)]">{compactId(event.actor_user_id)}</td><td className="px-5 py-3 text-xs text-[var(--color-ink-soft)]">{event.target_type ?? "—"} · {compactId(event.target_id)}</td><td className="px-5 py-3 text-xs text-[var(--color-muted)]">{details(event)}</td></tr>)}</tbody></table></div>}
    <PaginationControls pagination={page} isFetching={query.isFetching} onPageChange={(offset) => setFilters((current) => ({ ...current, offset }))} label={t("events")} />
  </section>;
}
