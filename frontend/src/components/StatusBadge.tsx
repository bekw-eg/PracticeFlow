import { useTranslation } from "react-i18next";

const STATUS_STYLES: Record<string, string> = {
  DRAFT: "bg-[var(--color-border)] text-[var(--color-ink-soft)]",
  PUBLISHED: "bg-[var(--color-brand-50)] text-[var(--color-brand-700)]",
  CLOSED: "bg-[var(--color-border)] text-[var(--color-ink-soft)]",
  RETIRED: "bg-[var(--color-border)] text-[var(--color-muted)]",
};

const STATUS_TRANSLATION_KEYS = {
  DRAFT: "statuses.DRAFT",
  PUBLISHED: "statuses.PUBLISHED",
  CLOSED: "statuses.CLOSED",
  RETIRED: "statuses.RETIRED",
} as const;

export function StatusBadge({ status }: { status: string }) {
  const { t } = useTranslation("common");
  const style = STATUS_STYLES[status] ?? "bg-[var(--color-border)] text-[var(--color-ink-soft)]";
  const key = STATUS_TRANSLATION_KEYS[status as keyof typeof STATUS_TRANSLATION_KEYS];
  const label = key ? t(key) : t("unknownStatus");

  return <span aria-label={label} className={`inline-flex items-center gap-1.5 rounded-[5px] border border-current/15 px-2.5 py-1 text-xs font-semibold ${style}`}><span aria-hidden="true" className="size-1.5 rounded-full bg-current opacity-75" />{label}</span>;
}
