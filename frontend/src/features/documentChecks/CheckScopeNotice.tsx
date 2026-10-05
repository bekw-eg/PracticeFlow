import { useTranslation } from "react-i18next";
import type { DocumentCheckResultSummary } from "../../types/api";

export function CheckScopeNotice({ summary }: { summary: DocumentCheckResultSummary }) {
  const { t } = useTranslation("documentChecks");
  const status = summary.first_page_exclusion;
  const message = status === "APPLIED" ? "firstPageSkipped"
    : status === "BOUNDARY_UNKNOWN" ? "firstPageBoundaryUnknown"
      : status === "NO_CONTENT" ? "noContentAfterFirstPage" : "previousCheckIncludesTitle";
  return <p className={`mt-2 text-xs ${status === "APPLIED" ? "text-[var(--color-muted)]" : "font-semibold text-amber-800"}`}>{t(message)}</p>;
}
