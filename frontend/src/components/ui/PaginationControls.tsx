import type { PaginationInfo } from "../../lib/pagination";

interface PaginationControlsProps {
  pagination: PaginationInfo;
  onPageChange: (offset: number) => void;
  isFetching?: boolean;
  label?: string;
}

export function PaginationControls({ pagination, onPageChange, isFetching = false, label = "Список" }: PaginationControlsProps) {
  if (pagination.total === 0) return null;
  const first = pagination.offset + 1;
  const last = Math.min(pagination.offset + pagination.limit, pagination.total);
  const canGoBack = pagination.offset > 0;

  return (
    <nav className="mt-5 flex flex-wrap items-center justify-between gap-3" aria-label={`Пагинация: ${label}`}>
      <p className="text-sm text-[var(--color-muted)]" aria-live="polite">
        {isFetching ? "Загрузка страницы…" : `${label}: ${first}–${last} из ${pagination.total}`}
      </p>
      <div className="flex gap-2">
        <button
          type="button"
          className="btn btn-secondary px-3 py-2 text-sm"
          disabled={!canGoBack || isFetching}
          onClick={() => onPageChange(Math.max(0, pagination.offset - pagination.limit))}
          aria-label="Предыдущая страница"
        >
          Назад
        </button>
        <button
          type="button"
          className="btn btn-secondary px-3 py-2 text-sm"
          disabled={!pagination.hasMore || isFetching}
          onClick={() => onPageChange(pagination.offset + pagination.limit)}
          aria-label="Следующая страница"
        >
          Далее
        </button>
      </div>
    </nav>
  );
}
