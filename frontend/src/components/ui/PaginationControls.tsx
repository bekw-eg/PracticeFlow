import type { PaginationInfo } from "../../lib/pagination";
import { useTranslation } from "react-i18next";
import { useLocaleFormatters } from "../../i18n/formatters";

interface PaginationControlsProps {
  pagination: PaginationInfo;
  onPageChange: (offset: number) => void;
  isFetching?: boolean;
  label?: string;
}

export function PaginationControls({ pagination, onPageChange, isFetching = false, label }: PaginationControlsProps) {
  const { t } = useTranslation("common");
  const { formatCount, formatNumber } = useLocaleFormatters();
  if (pagination.total === 0) return null;
  const listLabel = label ?? formatCount(pagination.total, (values) => t("itemCount", values));
  const first = pagination.offset + 1;
  const last = Math.min(pagination.offset + pagination.limit, pagination.total);
  const canGoBack = pagination.offset > 0;

  return (
    <nav className="mt-5 flex flex-wrap items-center justify-between gap-3" aria-label={t("pagination", { label: listLabel })}>
      <p className="text-sm text-[var(--color-muted)]" aria-live="polite">
        {isFetching ? t("loadingPage") : t("pageRange", { label: listLabel, first: formatNumber(first), last: formatNumber(last), total: formatNumber(pagination.total) })}
      </p>
      <div className="flex gap-2">
        <button
          type="button"
          className="btn btn-secondary px-3 py-2 text-sm"
          disabled={!canGoBack || isFetching}
          onClick={() => onPageChange(Math.max(0, pagination.offset - pagination.limit))}
          aria-label={t("previousPage")}
        >
          {t("back")}
        </button>
        <button
          type="button"
          className="btn btn-secondary px-3 py-2 text-sm"
          disabled={!pagination.hasMore || isFetching}
          onClick={() => onPageChange(pagination.offset + pagination.limit)}
          aria-label={t("nextPage")}
        >
          {t("next")}
        </button>
      </div>
    </nav>
  );
}
