import { CheckCircleIcon, ExclamationCircleIcon, ArrowPathIcon } from "@heroicons/react/24/solid";

export type SaveState = "idle" | "saving" | "saved" | "error";

export function SaveStatus({ state }: { state: SaveState }) {
  if (state === "idle") return null;
  if (state === "saving") {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs text-[var(--color-muted)]">
        <ArrowPathIcon className="size-3.5 animate-spin" />
        Сохранение…
      </span>
    );
  }
  if (state === "error") {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs text-[var(--color-danger-500)]">
        <ExclamationCircleIcon className="size-3.5" />
        Ошибка сохранения — есть несохранённые изменения
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-[var(--color-success-500)]">
      <CheckCircleIcon className="size-3.5" />
      Сохранено
    </span>
  );
}
