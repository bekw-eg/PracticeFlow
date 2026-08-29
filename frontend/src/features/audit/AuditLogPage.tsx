import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";

import { ErrorState, EmptyState, LoadingState } from "../../components/ui/StateViews";
import { PaginationControls } from "../../components/ui/PaginationControls";
import { fetchAuditEvents, verifyAuditIntegrity, type AuditFilters } from "./api";

const actions = ["", "MEMBERSHIP_CREATED", "MEMBERSHIP_ROLE_CHANGED", "MEMBERSHIP_DEACTIVATED", "REPORT_SUBMITTED", "REPORT_APPROVED", "REPORT_REVISION_REQUESTED", "EXPORT_REQUESTED", "EXPORT_DOWNLOADED", "MFA_ENROLLED", "MFA_RESET"];

function compactId(value: string | null) {
  return value ? `${value.slice(0, 8)}…${value.slice(-4)}` : "—";
}

function details(event: { metadata: Record<string, unknown> | null; sequence: number | null }) {
  const metadata = event.metadata ? Object.entries(event.metadata).map(([key, value]) => `${key}: ${String(value)}`).join(" · ") : "";
  return [event.sequence ? `#${event.sequence}` : "", metadata].filter(Boolean).join(" · ") || "—";
}

export function AuditLogPage() {
  const [filters, setFilters] = useState<AuditFilters>({ offset: 0 });
  const query = useQuery({ queryKey: ["audit-events", filters], queryFn: () => fetchAuditEvents(filters) });
  const integrity = useMutation({ mutationFn: verifyAuditIntegrity });
  const change = (key: Exclude<keyof AuditFilters, "offset">, value: string) => setFilters((current) => ({ ...current, offset: 0, [key]: value || undefined }));

  if (query.isLoading) return <LoadingState label="Загрузка журнала аудита…" />;
  if (query.isError) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  const page = query.data;
  if (!page) return <ErrorState message="Журнал аудита не вернул данные." onRetry={() => void query.refetch()} />;

  return <section className="space-y-5">
    <header className="card p-6"><div className="flex flex-wrap items-start justify-between gap-4"><div><h1 className="font-display text-2xl font-extrabold text-[var(--color-ink)]">Журнал аудита</h1><p className="mt-1 max-w-3xl text-sm leading-6 text-[var(--color-muted)]">События доступны только Super Admin текущей организации. В журнал не попадают пароли, токены, содержимое документов и имена файлов.</p></div><button type="button" className="btn btn-secondary" disabled={integrity.isPending} onClick={() => integrity.mutate()}>Проверить целостность</button></div>{integrity.data && <p className={`mt-4 rounded-xl px-4 py-3 text-sm ${integrity.data.valid ? "bg-emerald-50 text-emerald-800" : "bg-[var(--color-danger-50)] text-[var(--color-danger-500)]"}`} role="status">{integrity.data.valid ? `Цепочка проверена: ${integrity.data.checked_events} событий.` : `Нарушение цепочки на sequence ${integrity.data.first_invalid_sequence ?? "неизвестно"}.`}</p>}{integrity.isError && <p className="mt-4 text-sm text-[var(--color-danger-500)]" role="alert">Не удалось проверить целостность журнала. Повторите попытку.</p>}</header>
    <div className="card p-5"><div className="grid gap-3 md:grid-cols-3"><label><span className="form-label">Действие</span><select aria-label="Действие аудита" className="input" value={filters.action ?? ""} onChange={(event) => change("action", event.target.value)}>{actions.map((action) => <option key={action} value={action}>{action || "Все действия"}</option>)}</select></label><label><span className="form-label">С</span><input aria-label="Период с" type="datetime-local" className="input" value={filters.from ?? ""} onChange={(event) => change("from", event.target.value ? new Date(event.target.value).toISOString() : "")} /></label><label><span className="form-label">По</span><input aria-label="Период по" type="datetime-local" className="input" value={filters.to ?? ""} onChange={(event) => change("to", event.target.value ? new Date(event.target.value).toISOString() : "")} /></label><label><span className="form-label">Actor ID</span><input aria-label="Actor ID" className="input" value={filters.actor_id ?? ""} onChange={(event) => change("actor_id", event.target.value)} /></label><label><span className="form-label">Тип target</span><input aria-label="Тип target" className="input" value={filters.target_type ?? ""} onChange={(event) => change("target_type", event.target.value)} /></label><label><span className="form-label">Target ID</span><input aria-label="Target ID" className="input" value={filters.target_id ?? ""} onChange={(event) => change("target_id", event.target.value)} /></label></div></div>
    {page.items.length === 0 ? <EmptyState title="Событий по выбранным фильтрам нет" description="Измените период или снимите часть фильтров." /> : <div className="card overflow-x-auto"><table className="table-base min-w-[840px]"><thead><tr><th className="px-5 py-3">Время</th><th className="px-5 py-3">Действие</th><th className="px-5 py-3">Actor</th><th className="px-5 py-3">Target</th><th className="px-5 py-3">Безопасные детали</th></tr></thead><tbody>{page.items.map((event) => <tr key={event.id}><td className="whitespace-nowrap px-5 py-3 text-sm text-[var(--color-muted)]">{new Date(event.timestamp).toLocaleString()}</td><td className="px-5 py-3 font-mono-code text-xs text-[var(--color-ink)]">{event.action}</td><td className="px-5 py-3 font-mono-code text-xs text-[var(--color-muted)]">{compactId(event.actor_user_id)}</td><td className="px-5 py-3 text-xs text-[var(--color-ink-soft)]">{event.target_type ?? "—"} · {compactId(event.target_id)}</td><td className="px-5 py-3 text-xs text-[var(--color-muted)]">{details(event)}</td></tr>)}</tbody></table></div>}
    <PaginationControls pagination={page} isFetching={query.isFetching} onPageChange={(offset) => setFilters((current) => ({ ...current, offset }))} label="События" />
  </section>;
}
