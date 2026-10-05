import { CheckCircleIcon, ExclamationCircleIcon, ArrowPathIcon } from "@heroicons/react/24/solid";
import { useTranslation } from "react-i18next";

export type SaveState = "idle" | "saving" | "saved" | "error";

export function SaveStatus({ state }: { state: SaveState }) {
  const { t } = useTranslation("editor");
  if (state === "idle") return null;
  if (state === "saving") {
    return (
      <span role="status" aria-live="polite" className="inline-flex items-center gap-1.5 text-xs text-[var(--color-muted)]">
        <ArrowPathIcon className="size-3.5 animate-spin" aria-hidden="true" />
        {t("saving")}
      </span>
    );
  }
  if (state === "error") {
    return (
      <span role="status" aria-live="polite" className="inline-flex items-center gap-1.5 text-xs text-[var(--color-danger-500)]">
        <ExclamationCircleIcon className="size-3.5" aria-hidden="true" />
        {t("saveError")}
      </span>
    );
  }
  return (
    <span role="status" aria-live="polite" className="inline-flex items-center gap-1.5 text-xs text-[var(--color-success-500)]">
      <CheckCircleIcon className="size-3.5" aria-hidden="true" />
      {t("saved")}
    </span>
  );
}
