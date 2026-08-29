import type { Run } from "../../types/document";

export function RunView({ run }: { run: Run }) {
  if (run.kind === "text") {
    // Plain text deliberately remains a text node. Formatting wrappers are
    // semantic inline elements, so a Tiptap run can never turn into a block
    // or create an independently justified line in the A4 preview.
    let content: React.ReactNode = run.text;
    if (run.bold) content = <strong>{content}</strong>;
    if (run.italic) content = <em>{content}</em>;
    if (run.underline) content = <u>{content}</u>;
    return <>{content}</>;
  }
  if (run.kind === "variable") {
    return (
      <span className="rounded bg-[var(--color-brand-50)] px-1 text-[var(--color-brand-700)]">
        {run.resolved_text ?? `{{${run.key}}}`}
      </span>
    );
  }
  // pageNumber
  return <span className="text-[var(--color-muted)]">№</span>;
}
