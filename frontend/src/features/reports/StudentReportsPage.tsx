import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../../lib/api";
import { getApiErrorPresentation } from "../../lib/apiError";
import { DEFAULT_PAGE_SIZE, fetchPage } from "../../lib/pagination";
import { showToast } from "../../lib/toast";
import { StatusBadge } from "../../components/StatusBadge";
import { ExportButtons } from "../../components/ExportButtons";
import type { ReportDeadlineState, ReportOut, StudentReportOut } from "../../types/api";
import { ArrowRightIcon, CalendarDaysIcon, ClipboardDocumentListIcon, ClockIcon, PaperAirplaneIcon, UserGroupIcon } from "@heroicons/react/24/outline";
import { EmptyState, ErrorState, LoadingState } from "../../components/ui/StateViews";
import { PaginationControls } from "../../components/ui/PaginationControls";
import { useTranslation } from "react-i18next";
import { useLocaleFormatters } from "../../i18n/formatters";
import { useProductFeatures } from "../auth/useProductFeatures";

function useMyReports(offset: number) {
  return useQuery({
    queryKey: ["reports", { offset }],
    queryFn: () => fetchPage<StudentReportOut>("/reports", { offset, limit: DEFAULT_PAGE_SIZE }),
  });
}

function useSubmitReport() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (reportId: string) => (await api.post<ReportOut>(`/reports/${reportId}/submit`)).data,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["reports"] }),
  });
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function validationErrorsFrom(error: unknown): string[] {
  const response = asRecord(error)?.response;
  const detail = asRecord(asRecord(response)?.data)?.detail;
  const errors = asRecord(detail)?.errors;
  return Array.isArray(errors) ? errors.filter((message): message is string => typeof message === "string") : [];
}

function SubmitError({ error }: { error: unknown }) {
  const { t } = useTranslation("reports");
  const presentation = getApiErrorPresentation(error, "reports");
  const validationErrors = validationErrorsFrom(error);

  return (
    <div className="rounded-xl border border-[var(--color-danger-500)]/30 bg-[var(--color-danger-50)] px-4 py-3" role="alert" aria-live="assertive">
      <p className="text-sm font-semibold text-[var(--color-ink)]">{t("submitFailed")}</p>
      <p className="mt-1 text-sm leading-6 text-[var(--color-danger-500)]">{presentation.description}</p>
      {validationErrors.length > 0 && (
        <div className="mt-3 border-t border-[var(--color-danger-500)]/20 pt-3">
          <p className="text-sm font-medium text-[var(--color-ink)]">{t("submitChecklist")}</p>
          <ul className="mt-2 space-y-1 text-sm leading-5 text-[var(--color-ink-soft)]">
            {validationErrors.map((message, index) => <li key={`${message}-${index}`} className="flex gap-2"><span aria-hidden="true">•</span><span>{message}</span></li>)}
          </ul>
        </div>
      )}
    </div>
  );
}

function localDate(value: string) {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, month - 1, day);
}

function DeadlineStateBadge({ state }: { state: ReportDeadlineState }) {
  const { t } = useTranslation("reports");
  const states: Record<ReportDeadlineState, { label: string; className: string }> = {
    UPCOMING: { label: t("deadlineStates.upcoming"), className: "bg-[var(--color-surface)] text-[var(--color-muted)]" },
    DUE_SOON: { label: t("deadlineStates.dueSoon"), className: "bg-[var(--color-amber-50)] text-[var(--color-amber-500)]" },
    DUE_TODAY: { label: t("deadlineStates.dueToday"), className: "bg-[var(--color-amber-50)] text-[var(--color-amber-500)]" },
    OVERDUE: { label: t("deadlineStates.overdue"), className: "bg-[var(--color-danger-50)] text-[var(--color-danger-500)]" },
    SUBMITTED_ON_TIME: { label: t("deadlineStates.submittedOnTime"), className: "bg-[var(--color-success-50)] text-[var(--color-success-500)]" },
    SUBMITTED_LATE: { label: t("deadlineStates.submittedLate"), className: "bg-[var(--color-danger-50)] text-[var(--color-danger-500)]" },
  };
  const current = states[state];
  return <span role="status" className={`inline-flex rounded-[5px] border border-current/15 px-2.5 py-1 text-xs font-semibold ${current.className}`}>{current.label}</span>;
}

export function StudentReportsPage() {
  const { t } = useTranslation("reports");
  const { formatDate } = useLocaleFormatters();
  const { legacy_document_editor_enabled: legacyDocumentEditorEnabled } = useProductFeatures();
  const [searchParams, setSearchParams] = useSearchParams();
  const [submitErrors, setSubmitErrors] = useState<Record<string, unknown>>({});
  const offset = Math.max(0, Number(searchParams.get("offset") ?? "0") || 0);
  const { data: page, isLoading, isFetching, isError, error, refetch } = useMyReports(offset);
  const reports = page?.items ?? [];
  const submitReport = useSubmitReport();
  const submit = (reportId: string) => {
    setSubmitErrors((current) => {
      const { [reportId]: _removed, ...remaining } = current;
      return remaining;
    });
    submitReport.mutate(reportId, {
      onSuccess: () => showToast(t("submitSucceeded")),
      onError: (error) => setSubmitErrors((current) => ({ ...current, [reportId]: error })),
    });
  };
  const changePage = (nextOffset: number) => {
    const next = new URLSearchParams(searchParams);
    if (nextOffset === 0) next.delete("offset");
    else next.set("offset", String(nextOffset));
    setSearchParams(next);
  };

  return (
    <div>
      <header className="mb-7 border-b border-[var(--color-border)] pb-6">
        <p className="page-kicker">{t("student")}</p><h1 className="page-title mt-1">{t("myReports")}</h1><p className="page-description">{t("assignedReportsDescription")}</p>
      </header>

      {isLoading && <LoadingState label={t("loadingReports")} />}

      {isError && <ErrorState error={error} onRetry={() => void refetch()} />}

      {!isLoading && !isError && reports?.length === 0 && (
        <EmptyState title={t("noReports")} description={t("noReportsDescription")} />
      )}

      {reports.length > 0 && <div className="section-panel divide-y divide-[var(--color-border)] overflow-hidden">
        {!isError && reports?.map((report) => (
          <article key={report.id} className="bg-white p-5 sm:p-6">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-center gap-3"><div className="flex size-10 items-center justify-center rounded-[7px] border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-brand-600)]"><ClipboardDocumentListIcon className="size-5" /></div><div>
                <p className="font-display text-base font-bold text-[var(--color-ink)]">{report.internship_title}</p>
                <p className="mt-1 flex items-center gap-1.5 text-sm text-[var(--color-muted)]"><UserGroupIcon aria-hidden="true" className="size-4" />{t("groupLabel", { name: report.group_name })}</p>
                <p className="mt-1 font-mono-code text-xs text-[var(--color-muted)]">#{report.id.slice(0, 8)}</p>
              </div></div>
              <div className="flex flex-wrap items-center gap-2">
                <StatusBadge status={report.status} />
                <Link
                  to={`/reports/${report.id}/edit`}
                  className="btn btn-secondary"
                >
                  {legacyDocumentEditorEnabled && (report.status === "DRAFT" || report.status === "REVISION_REQUIRED") ? t("edit") : t("view")}<ArrowRightIcon className="size-4" />
                </Link>
                <ExportButtons reportId={report.id} compact />
                {(report.status === "DRAFT" || report.status === "REVISION_REQUIRED") && (
                  <button
                    onClick={() => submit(report.id)}
                    disabled={submitReport.isPending}
                    className="btn btn-primary"
                  >
                    <PaperAirplaneIcon className="size-4" />{t("submitForReview")}
                  </button>
                )}
              </div>
            </div>
            <div className="mt-4 flex flex-col gap-3 border-t border-[var(--color-border)] pt-4 text-sm sm:flex-row sm:items-center sm:justify-between">
              <div className="flex flex-wrap gap-x-5 gap-y-2 text-[var(--color-ink-soft)]"><p className="flex items-center gap-1.5"><CalendarDaysIcon aria-hidden="true" className="size-4 text-[var(--color-muted)]" />{t("periodLabel", { start: formatDate(localDate(report.start_date)), end: formatDate(localDate(report.end_date)) })}</p><p className="flex items-center gap-1.5"><ClockIcon aria-hidden="true" className="size-4 text-[var(--color-muted)]" />{t("deadlineLabel", { date: formatDate(localDate(report.deadline)) })}</p></div>
              <DeadlineStateBadge state={report.deadline_state} />
            </div>
            {report.internship_description && <section className="mt-4 border-l-2 border-[var(--color-brand-500)] bg-[var(--color-surface)] px-4 py-3"><p className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)]">{t("internshipInstructions")}</p><p className="mt-1 whitespace-pre-wrap text-sm leading-6 text-[var(--color-ink-soft)]">{report.internship_description}</p></section>}
            {submitErrors[report.id] !== undefined && <div className="mt-4"><SubmitError error={submitErrors[report.id]} /></div>}
          </article>
        ))}
      </div>}
      {!isError && page && <PaginationControls pagination={page} onPageChange={changePage} isFetching={isFetching} label={t("myReports")} />}
    </div>
  );
}
