import { ArrowPathIcon, InboxIcon, ExclamationTriangleIcon } from "@heroicons/react/24/outline";
import { getApiErrorPresentation } from "../../lib/apiError";
import { useTranslation } from "react-i18next";

export function LoadingState({ label }: { label?: string }) {
  const { t } = useTranslation("common");
  return <div className="loading-state" role="status" aria-live="polite"><ArrowPathIcon className="size-5 animate-spin text-[var(--color-brand-500)]" aria-hidden="true" />{label ?? t("loadingData")}</div>;
}

export function EmptyState({ title, description }: { title: string; description?: string }) {
  return <div className="empty-state"><div className="mx-auto flex size-10 items-center justify-center rounded-[7px] border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-brand-600)]"><InboxIcon aria-hidden="true" className="size-5" /></div><h2 className="mt-4 font-display text-base font-bold text-[var(--color-ink)]">{title}</h2>{description && <p className="mx-auto mt-1.5 max-w-md text-sm leading-6 text-[var(--color-muted)]">{description}</p>}</div>;
}

export function ErrorState({
  error,
  message,
  onRetry,
  compact = false,
}: {
  error?: unknown;
  message?: string;
  onRetry?: () => void;
  compact?: boolean;
}) {
  const { t } = useTranslation(["common", "errors"]);
  const presentation = error ? getApiErrorPresentation(error) : null;
  const title = presentation?.title ?? t("errors:loadFailed");
  const description = message ?? presentation?.description ?? t("errors:tryLater");

  return (
    <div className={`empty-state border-[var(--color-danger-500)]/30 ${compact ? "min-h-0 px-4 py-4 text-left" : ""}`} role="alert" aria-live="assertive">
      <div className={compact ? "flex items-start gap-3" : ""}>
        <div className={`${compact ? "shrink-0" : "mx-auto"} flex size-10 items-center justify-center rounded-[7px] bg-[var(--color-danger-50)] text-[var(--color-danger-500)]`}><ExclamationTriangleIcon className="size-5" aria-hidden="true" /></div>
        <div className={compact ? "min-w-0" : ""}>
          <h2 className={`${compact ? "text-sm" : "mt-4 text-base"} font-display font-bold text-[var(--color-ink)]`}>{title}</h2>
          <p className={`${compact ? "mt-1" : "mt-1.5"} text-sm leading-6 text-[var(--color-danger-500)]`}>{description}</p>
          {onRetry && <button type="button" onClick={onRetry} className="btn btn-secondary mt-3 px-3 py-2 text-sm text-[var(--color-brand-600)]"><ArrowPathIcon className="size-4" aria-hidden="true" />{t("common:retry")}</button>}
        </div>
      </div>
    </div>
  );
}
