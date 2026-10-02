import { useEffect, useState } from "react";
import { ChevronDownIcon, ChevronUpIcon } from "@heroicons/react/24/outline";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ErrorState, LoadingState } from "../../components/ui/StateViews";
import { PaginationControls } from "../../components/ui/PaginationControls";
import type { DocumentCheckFinding, TeacherDocumentSubmission } from "../../types/api";
import { useSubmissionFindings } from "./submissionApi";
import { CheckScopeNotice } from "./CheckScopeNotice";

const severityClasses: Record<DocumentCheckFinding["severity"], string> = {
  ERROR: "bg-[var(--color-danger-50)] text-[var(--color-danger-500)]",
  WARNING: "bg-amber-50 text-amber-800",
  INFO: "bg-[var(--color-brand-50)] text-[var(--color-brand-600)]",
};

function metric(value: Record<string, unknown>): string {
  if (Array.isArray(value.allowed)) return value.allowed.join(", ");
  if (value.name && "width_mm" in value && "height_mm" in value) return `${value.name} (${value.width_mm} × ${value.height_mm} mm)`;
  if ("width_mm" in value && "height_mm" in value) return `${value.width_mm} × ${value.height_mm} mm`;
  if (value.min !== undefined || value.max !== undefined) return `${value.min ?? "…"}–${value.max ?? "…"}${value.unit ? ` ${value.unit}` : ""}`;
  if ("value" in value) return `${value.value ?? "—"}${value.unit ? ` ${value.unit}` : ""}`;
  return "—";
}

export function SubmissionResult({ submission }: {
  submission: Pick<TeacherDocumentSubmission, "id" | "job" | "latest_completed_job">;
}) {
  const { t } = useTranslation(["documentChecks", "common"]);
  const [open, setOpen] = useState(false);
  const [offset, setOffset] = useState(0);
  const resultJob = submission.latest_completed_job ?? submission.job;
  useEffect(() => { setOffset(0); }, [resultJob.id]);
  const findings = useSubmissionFindings(
    submission.id, open && resultJob.status === "COMPLETED", offset, 25, resultJob.id,
  );
  const summary = resultJob.result_summary;
  const formatMetric = (value: Record<string, unknown>) => {
    if (typeof value.value === "boolean") return t(value.value ? "ruleValues.YES" : "ruleValues.NO");
    if (typeof value.value === "string" && ["LEFT", "CENTER", "RIGHT", "JUSTIFY", "PORTRAIT", "LANDSCAPE", "UNKNOWN"].includes(value.value)) return t(`ruleValues.${value.value}` as never);
    return metric(value).replace(/\bmm\b/g, t("unitMm")).replace(/\bpt\b/g, t("unitPt")).replace(/\bmultiple\b/g, t("unitMultiple"));
  };
  const findingLocation = (value: Record<string, unknown>): string => {
    if (value.paragraph_index) {
      const paragraph = t("findingParagraph", { number: Number(value.paragraph_index) });
      return value.run_index ? `${paragraph}, ${t("findingRun", { number: Number(value.run_index) })}` : paragraph;
    }
    if (value.section_index) return t("findingSection", { number: Number(value.section_index) });
    return t("findingDocument");
  };

  if (resultJob.status !== "COMPLETED" || !summary) return <Link className="font-semibold text-[var(--color-brand-600)]" to={`/document-checks/${submission.id}`}>{t("openReview")}</Link>;
  if (summary.first_page_exclusion === "BOUNDARY_UNKNOWN" || summary.first_page_exclusion === "NO_CONTENT") return <div className="min-w-56 max-w-sm text-sm"><CheckScopeNotice summary={summary} /><Link className="mt-2 inline-flex font-semibold text-[var(--color-brand-600)]" to={`/document-checks/${submission.id}`}>{t("openReview")}</Link></div>;
  if (summary.rules_evaluated === 0) return <div className="min-w-56 text-sm"><p className="font-semibold text-[var(--color-danger-500)]">{t("noRulesEvaluated")}</p><p className="mt-1 text-xs text-[var(--color-muted)]">{t("rulesChecked", { checked: 0, total: summary.rules_total })}</p><Link className="mt-2 inline-flex font-semibold text-[var(--color-brand-600)]" to={`/document-checks/${submission.id}`}>{t("openReview")}</Link></div>;
  return <div className="min-w-56 text-sm">
    {resultJob.id !== submission.job.id && <p className="mb-1 text-xs text-[var(--color-muted)]">{t("latestResult")} · {t("runNumber", { number: resultJob.run_number ?? 1 })}</p>}
    <CheckScopeNotice summary={summary} />
    <p className="font-semibold">{summary.findings_count ? t("findingsCount", { count: summary.findings_count }) : t("noFindings")}</p>
    <p className="mt-1 text-xs text-[var(--color-muted)]">{t("rulesChecked", { checked: summary.rules_evaluated, total: summary.rules_total })}</p>
    {summary.rules_skipped > 0 && <p className="mt-1 text-xs font-semibold text-amber-800">{t("rulesSkipped", { count: summary.rules_skipped })}</p>}
    {summary.findings_truncated && <p className="mt-1 text-xs font-semibold text-amber-800">{t("findingsTruncated")}</p>}
    <Link className="mt-2 mr-3 inline-flex font-semibold text-[var(--color-brand-600)]" to={`/document-checks/${submission.id}`}>{t("openReview")}</Link>
    <button type="button" className="mt-2 inline-flex items-center gap-1 font-semibold text-[var(--color-brand-600)]" aria-expanded={open} onClick={() => { setOpen((value) => !value); setOffset(0); }}>
      {open ? <ChevronUpIcon className="size-4" /> : <ChevronDownIcon className="size-4" />}{open ? t("hideFindings") : t("showFindings")}
    </button>
    {open && <div className="mt-3 min-w-[22rem] max-w-xl space-y-3">
      {findings.isLoading && <LoadingState label={t("loadingFindings")} />}
      {findings.isError && <ErrorState compact error={findings.error} onRetry={() => void findings.refetch()} />}
      {findings.data?.items.map((finding) => <article key={finding.id} className="rounded-xl border border-[var(--color-border)] p-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className={`rounded-full px-2 py-0.5 text-xs font-bold ${severityClasses[finding.severity]}`}>{t(`severities.${finding.severity}` as never)}</span>
          <strong>{t(`findingCodes.${finding.code}` as never, { defaultValue: finding.code })}</strong>
        </div>
        <p className="mt-1 text-xs text-[var(--color-muted)]">{findingLocation(finding.location)}</p>
        <dl className="mt-2 grid grid-cols-2 gap-2 text-xs"><div><dt className="font-semibold">{t("expected")}</dt><dd>{formatMetric(finding.expected)}</dd></div><div><dt className="font-semibold">{t("actual")}</dt><dd>{formatMetric(finding.actual)}</dd></div></dl>
      </article>)}
      {findings.data && <PaginationControls pagination={findings.data} onPageChange={setOffset} isFetching={findings.isFetching} label={t("checkFindings")} />}
    </div>}
  </div>;
}
