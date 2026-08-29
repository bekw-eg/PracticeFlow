const STATUS_STYLES: Record<string, string> = {
  DRAFT: "bg-[var(--color-border)] text-[var(--color-ink-soft)]",
  PUBLISHED: "bg-[var(--color-brand-50)] text-[var(--color-brand-700)]",
  SUBMITTED: "bg-[var(--color-amber-50)] text-[var(--color-amber-500)]",
  UNDER_REVIEW: "bg-[var(--color-amber-50)] text-[var(--color-amber-500)]",
  REVISION_REQUIRED: "bg-[var(--color-danger-50)] text-[var(--color-danger-500)]",
  APPROVED: "bg-[var(--color-success-50)] text-[var(--color-success-500)]",
  LOCKED: "bg-[var(--color-success-50)] text-[var(--color-success-500)]",
  CLOSED: "bg-[var(--color-border)] text-[var(--color-ink-soft)]",
};

const STATUS_LABELS_RU: Record<string, string> = {
  DRAFT: "Черновик",
  PUBLISHED: "Опубликовано",
  SUBMITTED: "Отправлено",
  UNDER_REVIEW: "На проверке",
  REVISION_REQUIRED: "Требует доработки",
  APPROVED: "Утверждено",
  LOCKED: "Утверждено и закрыто",
  CLOSED: "Завершено",
};

export function StatusBadge({ status }: { status: string }) {
  const style = STATUS_STYLES[status] ?? "bg-[var(--color-border)] text-[var(--color-ink-soft)]";
  const label = STATUS_LABELS_RU[status] ?? status;
  return <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ${style}`}><span className="size-1.5 rounded-full bg-current opacity-75" />{label}</span>;
}
