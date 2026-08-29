interface GroupCodeChipProps {
  code: string;
  size?: "sm" | "md";
}

/**
 * The one recurring visual motif of the app: a group's name (e.g. "BK2405")
 * rendered like an academic course code — bordered, monospace, slightly
 * tracked-out. It appears in the sidebar, the breadcrumb, and internship
 * cards, so a teacher always sees the same "object" representing the group
 * they're inside of, everywhere PracticeFlow shows it.
 */
export function GroupCodeChip({ code, size = "md" }: GroupCodeChipProps) {
  const sizeClasses = size === "sm" ? "text-xs px-2 py-0.5" : "text-sm px-2.5 py-1";
  return (
    <span
      className={`font-mono-code inline-flex items-center rounded-md border border-[var(--color-border)] bg-[var(--color-brand-50)] text-[var(--color-brand-700)] font-semibold tracking-wide ${sizeClasses}`}
    >
      {code}
    </span>
  );
}
