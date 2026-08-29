import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../../lib/api";
import { DEFAULT_PAGE_SIZE, fetchPage } from "../../lib/pagination";
import { StatusBadge } from "../../components/StatusBadge";
import { ExportButtons } from "../../components/ExportButtons";
import type { ReportOut } from "../../types/api";
import { ArrowRightIcon, ClipboardDocumentListIcon, PaperAirplaneIcon } from "@heroicons/react/24/outline";
import { EmptyState, ErrorState, LoadingState } from "../../components/ui/StateViews";
import { PaginationControls } from "../../components/ui/PaginationControls";

function useMyReports(offset: number) {
  return useQuery({
    queryKey: ["reports", { offset }],
    queryFn: () => fetchPage<ReportOut>("/reports", { offset, limit: DEFAULT_PAGE_SIZE }),
  });
}

function useSubmitReport() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (reportId: string) => (await api.post<ReportOut>(`/reports/${reportId}/submit`)).data,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["reports"] }),
  });
}

export function StudentReportsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const offset = Math.max(0, Number(searchParams.get("offset") ?? "0") || 0);
  const { data: page, isLoading, isFetching, isError, error, refetch } = useMyReports(offset);
  const reports = page?.items ?? [];
  const submitReport = useSubmitReport();
  const changePage = (nextOffset: number) => {
    const next = new URLSearchParams(searchParams);
    if (nextOffset === 0) next.delete("offset");
    else next.set("offset", String(nextOffset));
    setSearchParams(next);
  };

  return (
    <div>
      <header className="mb-7">
        <p className="page-kicker">Студент</p><h1 className="page-title mt-1">Мои отчёты</h1><p className="page-description">Отчёты по практике, назначенные вашим преподавателем.</p>
      </header>

      {isLoading && <LoadingState label="Загрузка отчётов…" />}

      {isError && <ErrorState error={error} onRetry={() => void refetch()} />}

      {!isLoading && !isError && reports?.length === 0 && (
        <EmptyState title="Отчётов пока нет" description="Когда преподаватель опубликует практику для вашей группы, отчёт появится здесь." />
      )}

      <div className="space-y-3">
        {!isError && reports?.map((report) => (
          <div key={report.id} className="card flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-3"><div className="flex size-11 items-center justify-center rounded-xl bg-[var(--color-brand-50)] text-[var(--color-brand-600)]"><ClipboardDocumentListIcon className="size-5" /></div><div>
              <p className="font-mono-code text-xs text-[var(--color-muted)]">#{report.id.slice(0, 8)}</p>
              <div className="mt-1.5">
                <StatusBadge status={report.status} />
              </div>
            </div></div>
            <div className="flex flex-wrap items-center gap-2">
              <Link
                to={`/reports/${report.id}/edit`}
                className="btn btn-secondary"
              >
                {report.status === "DRAFT" || report.status === "REVISION_REQUIRED" ? "Редактировать" : "Просмотреть"}<ArrowRightIcon className="size-4" />
              </Link>
              <ExportButtons reportId={report.id} compact />
              {(report.status === "DRAFT" || report.status === "REVISION_REQUIRED") && (
                <button
                  onClick={() => submitReport.mutate(report.id)}
                  disabled={submitReport.isPending}
                  className="btn btn-primary"
                >
                  <PaperAirplaneIcon className="size-4" />Отправить на проверку
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
      {!isError && page && <PaginationControls pagination={page} onPageChange={changePage} isFetching={isFetching} label="Отчёты" />}
    </div>
  );
}
