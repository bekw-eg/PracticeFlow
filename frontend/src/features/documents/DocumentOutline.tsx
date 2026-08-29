import type { DocumentModel } from "../../types/document";

/** Renders a heading tree (sections -> their heading blocks) with server
 * numbering, and scrolls to the corresponding element on click. Doubles as
 * the foundation for a future automatic Table of Contents. */
export function DocumentOutline({ document, numbering }: { document: DocumentModel; numbering: Record<string, string> }) {
  const scrollTo = (id: string) => {
    globalThis.document.getElementById(`node-${id}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <div className="card p-4">
      <div className="mb-2 flex items-center justify-between"><h3 className="font-display text-sm font-bold text-[var(--color-ink)]">Оглавление</h3><span className="rounded-full bg-[var(--color-surface)] px-2 py-0.5 text-[10px] font-semibold text-[var(--color-muted)]">{document.sections.length}</span></div>
      <nav className="space-y-1 text-sm">
        {document.sections.map((section) => (
          <div key={section.id}>
            <button
              type="button"
              onClick={() => scrollTo(section.id)}
              className="block w-full truncate rounded-lg px-2 py-1.5 text-left text-[var(--color-ink-soft)] transition-colors hover:bg-[var(--color-brand-50)] hover:text-[var(--color-brand-600)]"
            >
              <span className="mr-1.5 text-[var(--color-muted)]">{numbering[section.id]}</span>
              {section.title}
            </button>
            {section.blocks
              .filter((b) => b.type === "heading")
              .map((heading) => (
                <button
                  key={heading.id}
                  type="button"
                  onClick={() => scrollTo(heading.id)}
                  className="block w-full truncate rounded-lg py-1 pl-7 pr-2 text-left text-xs text-[var(--color-muted)] transition-colors hover:bg-[var(--color-brand-50)] hover:text-[var(--color-brand-600)]"
                >
                  {numbering[heading.id] && <span className="mr-1.5">{numbering[heading.id]}</span>}
                  {"runs" in heading ? heading.runs.map((r) => (r.kind === "text" ? r.text : "")).join("") || "Без названия" : ""}
                </button>
              ))}
          </div>
        ))}
      </nav>
    </div>
  );
}
