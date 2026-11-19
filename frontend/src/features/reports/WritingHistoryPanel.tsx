import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { ErrorState, LoadingState } from "../../components/ui/StateViews";
import { useLocaleFormatters } from "../../i18n/formatters";
import { api } from "../../lib/api";
import type { WritingHistory } from "../../types/api";

const CHART_HEIGHT = 72;

function useWritingHistory(reportId: string | undefined) {
  return useQuery({
    queryKey: ["reports", reportId, "writing-history"],
    queryFn: async () => (await api.get<WritingHistory>(`/reports/${reportId}/writing-history`)).data,
    enabled: !!reportId,
  });
}

/** Word count per day as bars; days with a large single-save jump are marked. */
function WritingChart({ history }: { history: WritingHistory }) {
  const { t } = useTranslation("reports");
  const { formatDate, formatNumber } = useLocaleFormatters();
  const max = Math.max(1, ...history.days.map((day) => day.word_count));
  const width = Math.max(history.days.length * 14, 120);
  const bar = width / history.days.length;
  return (
    <figure className="mt-4">
      <svg role="img" aria-label={t("writingHistory.chartLabel")} viewBox={`0 0 ${width} ${CHART_HEIGHT}`} preserveAspectRatio="none" className="h-20 w-full">
        {history.days.map((day, index) => {
          const height = Math.max(2, (day.word_count / max) * (CHART_HEIGHT - 4));
          const large = day.largest_save_words >= history.large_save_threshold;
          return (
            <rect
              key={day.date}
              data-large-save={large || undefined}
              x={index * bar + bar * 0.15}
              y={CHART_HEIGHT - height}
              width={bar * 0.7}
              height={height}
              rx={1.5}
              className={large ? "fill-[var(--color-amber-500)]" : "fill-[var(--color-brand-500)]"}
            >
              <title>{t("writingHistory.dayLabel", { date: formatDate(day.date), words: formatNumber(day.word_count), added: formatNumber(day.words_added) })}</title>
            </rect>
          );
        })}
      </svg>
      <figcaption className="sr-only">
        <ul>
          {history.days.map((day) => (
            <li key={day.date}>{t("writingHistory.dayLabel", { date: formatDate(day.date), words: formatNumber(day.word_count), added: formatNumber(day.words_added) })}</li>
          ))}
        </ul>
      </figcaption>
    </figure>
  );
}

export function WritingHistoryPanel({ reportId }: { reportId: string }) {
  const { t } = useTranslation("reports");
  const { formatNumber } = useLocaleFormatters();
  const query = useWritingHistory(reportId);
  const history = query.data;

  return (
    <section className="card p-5" aria-labelledby="writing-history-title">
      <h2 id="writing-history-title" className="font-display text-lg font-bold text-[var(--color-ink)]">{t("writingHistory.title")}</h2>
      <p className="mt-1 text-xs text-[var(--color-muted)]">{t("writingHistory.hint")}</p>
      {query.isLoading && <LoadingState />}
      {query.isError && <ErrorState compact error={query.error} message={t("writingHistory.loadError")} onRetry={() => void query.refetch()} />}
      {history && history.days.length === 0 && <p className="mt-4 text-sm text-[var(--color-muted)]">{t("writingHistory.empty")}</p>}
      {history && history.days.length > 0 && (
        <>
          <WritingChart history={history} />
          <ul className="mt-3 space-y-1 text-sm text-[var(--color-ink-soft)]">
            <li>{t("writingHistory.words", { value: formatNumber(history.current_words ?? 0) })}</li>
            <li>{t("writingHistory.activeDays", { value: formatNumber(history.active_days) })}</li>
            <li>{t("writingHistory.saves", { value: formatNumber(history.total_saves) })}</li>
          </ul>
          {history.largest_save_words >= history.large_save_threshold && (
            <p className="mt-3 rounded-[5px] bg-[var(--color-amber-50)] px-3 py-2 text-xs font-medium text-[var(--color-amber-500)]" role="note">
              {t("writingHistory.largeSave", { value: formatNumber(history.largest_save_words) })}
            </p>
          )}
        </>
      )}
    </section>
  );
}
