import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { ArrowDownTrayIcon, ArrowLeftIcon, DocumentTextIcon } from "@heroicons/react/24/outline";
import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { PaginationControls } from "../../components/ui/PaginationControls";
import { ErrorState, LoadingState } from "../../components/ui/StateViews";
import { useLocaleFormatters } from "../../i18n/formatters";
import type { DocumentCheckFinding, DocumentCheckJob, DocumentSettings, LocalPlagiarismMatch, ParagraphType } from "../../types/api";
import {
  downloadTeacherSubmissionOriginal,
  useAllSubmissionFindings,
  useTeacherDocumentPreview,
  useTeacherDocumentSubmission,
  useDocumentSettings, useSaveDocumentSettings, useRecheckDocument,
  useDocumentParagraphs, useDocumentRuns, useDocumentRun, useAllLocalPlagiarismMatches, useLocalPlagiarismRuns, useUpdateDocumentLifecycle, useDeleteDocumentOriginal,
} from "./submissionApi";
import { PaginatedDocument, type FindingPosition } from "./PaginatedDocument";
import { DocumentChecksGate } from "./DocumentChecksGate";
import { CheckScopeNotice } from "./CheckScopeNotice";
import { DocumentRulesPanel } from "./DocumentRulesPanel";
import { TeacherReviewPanel } from "./TeacherReviewPanel";
import { RuleConfigFields } from "./RuleConfigFields";

const EMPTY_FINDINGS: DocumentCheckFinding[] = [];
const EMPTY_SIMILARITY_MATCHES: LocalPlagiarismMatch[] = [];
const PAGE_SIZE = 25;

const severityClasses: Record<DocumentCheckFinding["severity"], string> = {
  ERROR: "border-[var(--color-danger-500)] bg-[var(--color-danger-50)]",
  WARNING: "border-amber-400 bg-amber-50",
  INFO: "border-[var(--color-brand-500)] bg-[var(--color-brand-50)]",
};

function metric(value: Record<string, unknown>): string {
  if (Array.isArray(value.allowed)) return value.allowed.join(", ");
  if (value.name && "width_mm" in value && "height_mm" in value) return `${value.name} (${value.width_mm} × ${value.height_mm} mm)`;
  if ("width_mm" in value && "height_mm" in value) return `${value.width_mm} × ${value.height_mm} mm`;
  if (value.min !== undefined || value.max !== undefined) return `${value.min ?? "…"}–${value.max ?? "…"}${value.unit ? ` ${value.unit}` : ""}`;
  if ("value" in value) return `${value.value ?? "—"}${value.unit ? ` ${value.unit}` : ""}`;
  return "—";
}

export function TeacherDocumentReviewPage() {
  const { submissionId } = useParams<{ submissionId: string }>();
  return <DocumentChecksGate><TeacherDocumentReview key={submissionId} submissionId={submissionId} /></DocumentChecksGate>;
}

function TeacherDocumentReview({ submissionId }: { submissionId: string | undefined }) {
  const { t } = useTranslation(["documentChecks", "common"]);
  const { formatDateTime, formatFileSize, formatNumber } = useLocaleFormatters();
  const submission = useTeacherDocumentSubmission(submissionId);
  const preview = useTeacherDocumentPreview(submissionId, !!submission.data && !submission.data.lifecycle?.original_delete_requested_at);
  const settings = useDocumentSettings(submissionId);
  const paragraphs = useDocumentParagraphs(submissionId, !!submission.data && !submission.data.lifecycle?.original_delete_requested_at);
  const save = useSaveDocumentSettings(submissionId ?? "");
  const recheck = useRecheckDocument(submissionId ?? "");
  const lifecycle = useUpdateDocumentLifecycle(submissionId ?? "");
  const removeOriginal = useDeleteDocumentOriginal(submissionId ?? "");
  const runs = useDocumentRuns(submissionId, submission.data?.job.id, submission.data?.job.status);
  const similarityRuns = useLocalPlagiarismRuns(submissionId, submission.data?.job.id, submission.data?.job.status);
  const [draft, setDraft] = useState<DocumentSettings | null>(null);
  const [dirty, setDirty] = useState(false);
  const [tab, setTab] = useState<"remarks" | "similarity" | "rules">("remarks");
  const [selectedRunId, setSelectedRunId] = useState("");
  const [selectedParagraph, setSelectedParagraph] = useState<{ index: number; text: string } | null>(null);
  const [visibleResult, setVisibleResult] = useState<{ job: DocumentCheckJob; findings: DocumentCheckFinding[] } | null>(null);
  const [showRunRules, setShowRunRules] = useState(false);
  const runDetail = useDocumentRun(submissionId, visibleResult?.job.id, showRunRules);
  const recheckKey = useRef<{ revision: number; key: string } | null>(null);
  const requestBusy = useRef(false);
  const [preparing, setPreparing] = useState(false);
  const busy = preparing || save.isPending || recheck.isPending || lifecycle.isPending || removeOriginal.isPending;
  const latestCompleted = submission.data?.latest_completed_job ?? (submission.data?.job.status === "COMPLETED" ? submission.data.job : undefined);
  const resultJob = selectedRunId ? runs.data?.find(job => job.id === selectedRunId) : latestCompleted;
  const similarityRun = similarityRuns.data?.find(run => run.job_id === resultJob?.id);
  const similarityMatches = useAllLocalPlagiarismMatches(
    submissionId ?? "", similarityRun?.id, similarityRun?.status === "COMPLETED",
  );
  const similarityMarkers = useMemo<DocumentCheckFinding[]>(() => (similarityMatches.data ?? EMPTY_SIMILARITY_MATCHES).map((match) => ({
    id: match.id, check_rule_id: null, run_rule_id: null, sequence: match.sequence,
    rule_type: "REFERENCES", category: "local_similarity", severity: "WARNING",
    code: "LOCAL_TEXT_MATCH", property_name: "local_similarity",
    location: { paragraph_index: match.target_paragraph_index },
    expected: { value: "original text" }, actual: { value: `${match.matched_word_count} words` }, finding_schema_version: 1,
  })), [similarityMatches.data]);
  useEffect(() => {
    if (settings.data && !dirty) setDraft(current => !current || current.revision <= settings.data.revision ? settings.data : current);
  }, [settings.data, dirty]);
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  const paragraphTypes = useMemo(() => Object.fromEntries((paragraphs.data ?? []).map(item => [item.paragraph_index,
    draft?.paragraph_overrides[String(item.paragraph_index)] ?? item.automatic_type])) as Record<number, ParagraphType>, [paragraphs.data, draft?.paragraph_overrides]);
  const [offset, setOffset] = useState(0);
  const [selectedFinding, setSelectedFinding] = useState<string | null>(null);
  const [selectedSimilarityMatch, setSelectedSimilarityMatch] = useState<string | null>(null);
  const [positions, setPositions] = useState<Record<string, FindingPosition>>({});
  const findingsPanel = useRef<HTMLDivElement>(null);
  const findings = useAllSubmissionFindings(
    submissionId ?? "",
    resultJob?.status === "COMPLETED",
    resultJob?.id,
  );
  const download = useMutation({ mutationFn: downloadTeacherSubmissionOriginal });
  const allFindings = visibleResult?.findings ?? EMPTY_FINDINGS;
  useEffect(() => {
    // Promote a result only when its complete list is ready. A late response for
    // another job has a different query key and cannot replace this result.
    if (resultJob?.status === "COMPLETED" && findings.data) {
      setVisibleResult(current => !selectedRunId && current && (current.job.run_number ?? 1) > (resultJob.run_number ?? 1)
        ? current : { job: resultJob, findings: findings.data });
    }
  }, [resultJob, findings.data, selectedRunId]);
  useEffect(() => { setSelectedFinding(null); setOffset(0); }, [visibleResult?.job.id]);
  const focusFinding = useCallback((id: string) => {
    setTab("remarks");
    setSelectedFinding(id);
    const index = allFindings.findIndex((finding) => finding.id === id);
    if (index >= 0) setOffset(Math.floor(index / PAGE_SIZE) * PAGE_SIZE);
  }, [allFindings]);
  const focusSimilarity = useCallback((id: string) => {
    setTab("similarity");
    setSelectedSimilarityMatch(id);
  }, []);

  const saveCurrent = async (andRecheck: boolean, keepMine = false) => {
    if (!draft || requestBusy.current) return;
    requestBusy.current = true;
    setPreparing(true);
    try {
      let saved = draft;
      if (keepMine) {
        const latest = await settings.refetch();
        if (!latest.data || latest.isError) return;
        saved = { ...draft, revision: latest.data.revision };
      }
      if (dirty || keepMine) {
        saved = await save.mutateAsync(saved);
        setDraft(saved);
        setDirty(false);
      }
      if (andRecheck) {
        if (recheckKey.current?.revision !== saved.revision) recheckKey.current = { revision: saved.revision, key: crypto.randomUUID() };
        await recheck.mutateAsync({ revision: saved.revision, idempotencyKey: recheckKey.current.key });
        recheckKey.current = null;
        setSelectedRunId("");
        setTab("remarks");
      }
    } catch {
      // Preserve edits and the request key so an uncertain retry stays idempotent.
    } finally {
      requestBusy.current = false;
      setPreparing(false);
    }
  };
  const formatMetric = (value: Record<string, unknown>) => {
    if (typeof value.value === "boolean") return t(value.value ? "ruleValues.YES" : "ruleValues.NO");
    if (typeof value.value === "string" && ["LEFT", "CENTER", "RIGHT", "JUSTIFY", "PORTRAIT", "LANDSCAPE", "UNKNOWN"].includes(value.value)) {
      return t(`ruleValues.${value.value}` as never);
    }
    return metric(value).replace(/\bmm\b/g, t("unitMm")).replace(/\bpt\b/g, t("unitPt")).replace(/\bmultiple\b/g, t("unitMultiple"));
  };
  useEffect(() => {
    const card = Array.from(findingsPanel.current?.querySelectorAll<HTMLElement>("[data-finding-card]") ?? [])
      .find((element) => element.dataset.findingCard === selectedFinding);
    if (card && findingsPanel.current) {
      const panel = findingsPanel.current;
      panel.scrollTo({ top: panel.scrollTop + card.getBoundingClientRect().top - panel.getBoundingClientRect().top - 12, behavior: "smooth" });
    }
  }, [selectedFinding, offset]);

  const locationText = (finding: DocumentCheckFinding) => {
    const position = positions[finding.id];
    const details: string[] = [];
    if (position?.pages.length) details.push(t("findingPages", { pages: position.pages.join(", ") }));
    if (finding.location.section_index) details.push(t("findingSection", { number: Number(finding.location.section_index) }));
    if (finding.location.paragraph_index) details.push(t("findingParagraph", { number: Number(finding.location.paragraph_index) }));
    if (finding.location.run_index) details.push(t("findingRun", { number: Number(finding.location.run_index) }));
    if (position && !position.pages.length) details.push(t("locationUnavailable"));
    return details.join(" · ") || t("findingDocument");
  };

  if (submission.isLoading) return <LoadingState label={t("loadingCheck")} />;
  if (!submission.data) return <ErrorState error={submission.error} onRetry={() => void submission.refetch()} />;
  const item = submission.data;
  const originalUnavailable = Boolean(item.lifecycle?.original_delete_requested_at);
  const originalDeleted = Boolean(item.lifecycle?.original_deleted_at);
  const lifecycleRevision = item.lifecycle?.revision ?? 0;
  const summary = visibleResult?.job.result_summary;
  const active = item.job.status === "QUEUED" || item.job.status === "PROCESSING";
  const activeSameRevision = active && item.job.settings_revision === draft?.revision && !dirty;

  return <div>
    <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
      <div>
        <Link to={item.review_group_id ? `/review-groups/${item.review_group_id}` : "/document-checks"} className="inline-flex items-center gap-1.5 text-sm font-semibold text-[var(--color-muted)]"><ArrowLeftIcon className="size-4" />{t(item.review_group_id ? "reviewGroups.backToGroup" : "backToChecks")}</Link>
        <h1 className="page-title mt-3 break-words">{item.original_filename}</h1>
        <p className="mt-1 text-sm text-[var(--color-muted)]">{item.student_label || t("notSpecified")} · {formatDateTime(item.submitted_at)} · {formatFileSize(item.size_bytes)}</p>
      </div>
      <button type="button" className="btn btn-secondary" disabled={download.isPending || originalUnavailable} onClick={() => download.mutate(item)}><ArrowDownTrayIcon className="size-4" />{t("downloadOriginal")}</button>
    </div>
    {download.isError && <div className="mb-4"><ErrorState compact error={download.error} /></div>}
    {submission.isError && <div className="mb-4"><ErrorState compact error={submission.error} onRetry={() => void submission.refetch()} /></div>}
    {originalUnavailable && <div className="mb-4 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">{item.lifecycle?.original_deleted_at ? t("originalUnavailable") : t("originalRemovalPending")}</div>}
    <div className="mb-5 flex flex-wrap items-center gap-2 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3 text-sm">
      <button type="button" className="btn btn-secondary px-3 py-2" disabled={busy} onClick={() => lifecycle.mutate({ revision: lifecycleRevision, archived: !item.lifecycle?.archived, disclosure_allowed: item.lifecycle?.disclosure_allowed ?? item.plagiarism_source_disclosure_allowed })}>{item.lifecycle?.archived ? t("restoreDocument") : t("archiveDocument")}</button>
      <button type="button" className="btn btn-secondary px-3 py-2" disabled={busy || originalUnavailable} onClick={() => lifecycle.mutate({ revision: lifecycleRevision, archived: item.lifecycle?.archived ?? false, disclosure_allowed: !(item.lifecycle?.disclosure_allowed ?? item.plagiarism_source_disclosure_allowed) })}>{(item.lifecycle?.disclosure_allowed ?? item.plagiarism_source_disclosure_allowed) ? t("sourceDisclosureAllowed") : t("allowSourceDisclosure")}</button>
      <button type="button" className="btn btn-secondary px-3 py-2" disabled={busy || originalDeleted} onClick={() => { if (window.confirm(t("removeOriginalConfirm"))) removeOriginal.mutate(lifecycleRevision); }}>{originalUnavailable ? t("originalRemovalPending") : t("removeOriginal")}</button>
      {lifecycle.isError && <ErrorState compact error={lifecycle.error} />}
      {removeOriginal.isError && <ErrorState compact error={removeOriginal.error} />}
    </div>

    <TeacherReviewPanel submission={item} viewedJob={visibleResult?.job}
      ready={!!visibleResult && visibleResult.job.id === resultJob?.id && !findings.isLoading && !findings.isError && tab === "remarks"}
      onShowReviewedRun={id => { setSelectedRunId(id); setTab("remarks"); }} />
    <div className="grid items-start gap-5 lg:grid-cols-[350px_minmax(0,1fr)] xl:grid-cols-[390px_minmax(0,1fr)]">
      <aside className="card flex flex-col overflow-hidden lg:sticky lg:top-24 lg:max-h-[calc(100vh-7rem)]">
        <div className="shrink-0 border-b border-[var(--color-border)] px-4 py-4">
          <div role="tablist" aria-label={t("documentReviewSections")} className="mb-3 flex gap-2">
            {(["remarks", "similarity", "rules"] as const).map(value => <button key={value} id={`document-tab-${value}`} aria-controls={`document-panel-${value}`} role="tab" aria-selected={tab === value}
              className={`btn flex-1 ${tab === value ? "btn-primary" : "btn-secondary"}`} onClick={() => setTab(value)}>{t(value === "rules" ? "documentRules" : value === "similarity" ? "localSimilarity" : "remarks")}</button>)}
          </div>
          <p role="status" className={`text-xs ${dirty ? "font-semibold text-amber-900" : "text-[var(--color-muted)]"}`}>
            {busy ? t("settingsSaving") : dirty ? t("documentSettingsUnsaved") : draft ? t("documentSettingsSaved", { revision: draft.revision }) : t("settingsLoading")}
          </p>
          {visibleResult && <p className="mt-1 text-xs text-[var(--color-muted)]">{t("resultRevision", { run: visibleResult.job.run_number ?? 1, revision: visibleResult.job.settings_revision ?? t("originalProfile") })}</p>}
          {draft && (visibleResult?.job.settings_revision !== draft.revision || dirty) && <p className="mt-2 text-xs text-amber-900">{t("recheckNeeded")}</p>}
          <div className="mt-3 flex flex-wrap gap-2">
            <button type="button" className="btn btn-secondary" disabled={busy || originalUnavailable || !dirty || !draft} onClick={() => void saveCurrent(false)}>{t("common:save")}</button>
            <button type="button" className="btn btn-primary flex-1" disabled={busy || originalUnavailable || !draft || activeSameRevision} onClick={() => void saveCurrent(true)}>{t("recheck")}</button>
          </div>
          {active && <p role="status" className="mt-2 text-xs font-semibold">{t(`jobStatuses.${item.job.status}`)} · {t("runNumber", { number: item.job.run_number ?? 1 })}</p>}
          {(save.isError || recheck.isError) && <div className="mt-3 space-y-2"><p role="alert" className="text-xs text-[var(--color-danger-500)]">{t(save.isError ? "settingsSaveFailed" : "recheckFailed")}</p><ErrorState compact error={save.error ?? recheck.error} />
            <button type="button" className="text-xs font-semibold underline" disabled={busy} onClick={() => void saveCurrent(false, true)}>{t("saveMySettings")}</button></div>}
          {dirty && <button type="button" className="mt-2 text-xs underline" disabled={busy} onClick={async () => {
            const latest = await settings.refetch();
            if (latest.data && !latest.isError) { setDraft(latest.data); setDirty(false); save.reset(); recheck.reset(); }
          }}>{t("reloadSavedSettings")}</button>}
          <div className={tab === "remarks" ? "mt-3" : "hidden"}>
          <p className="mt-1 text-xs text-[var(--color-muted)]">{summary ? t("rulesChecked", { checked: summary.rules_evaluated, total: summary.rules_total }) : t(`jobStatuses.${item.job.status}`)}</p>
          {summary && <CheckScopeNotice summary={summary} />}
          {summary && summary.rules_evaluated > 0 && <p className="mt-2 text-sm font-semibold">{t("findingsCount", { count: summary.findings_count })}</p>}
          {!!summary?.rules_skipped && summary.rules_evaluated > 0 && <p className="mt-2 text-xs text-amber-800">{t("rulesSkipped", { count: summary.rules_skipped })}</p>}
          {summary?.findings_truncated && <p className="mt-2 text-xs text-amber-800">{t("findingsTruncated")}</p>}
          </div>
        </div>
        <div hidden={tab !== "rules"} role="tabpanel" id="document-panel-rules" aria-labelledby="document-tab-rules" className="min-h-0 max-h-[55vh] space-y-3 overflow-y-auto p-3 lg:max-h-[calc(100vh-27rem)]">
          {settings.isLoading && <LoadingState label={t("settingsLoading")} />}
          {settings.isError && <ErrorState compact error={settings.error} onRetry={() => void settings.refetch()} />}
          {paragraphs.isError && <ErrorState compact error={paragraphs.error} onRetry={() => void paragraphs.refetch()} />}
          {draft && <DocumentRulesPanel draft={draft} disabled={busy} onChange={next => { setDraft(next); setDirty(true); }} paragraphs={paragraphs.data ?? []} selectedParagraph={selectedParagraph} />}
        </div>
        <div hidden={tab !== "similarity"} role="tabpanel" id="document-panel-similarity" aria-labelledby="document-tab-similarity" className="min-h-0 max-h-[55vh] space-y-3 overflow-y-auto p-3 lg:max-h-[calc(100vh-27rem)]">
          <p className="text-xs text-[var(--color-muted)]">{t("localSimilarityDescription")}</p>
          {similarityRuns.isLoading && <LoadingState label={t("similarityLoading")} />}
          {similarityRuns.isError && <ErrorState compact error={similarityRuns.error} onRetry={() => void similarityRuns.refetch()} />}
          {!similarityRun && resultJob?.status === "COMPLETED" && <p className="rounded-xl bg-amber-50 p-3 text-sm text-amber-900">{t("similarityUnavailable")}</p>}
          {(similarityRun?.status === "QUEUED" || similarityRun?.status === "PROCESSING") && <LoadingState label={t("similarityChecking")} />}
          {similarityRun?.status === "FAILED" && <p className="rounded-xl bg-[var(--color-danger-50)] p-3 text-sm text-[var(--color-danger-500)]">{t("similarityUnavailable")}</p>}
          {similarityRun?.status === "COMPLETED" && <>
            <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)]">{t("similarityPercentage")}</p>
              <p className="mt-1 text-3xl font-bold text-[var(--color-brand-700)]">{formatNumber(similarityRun.similarity_percent, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%</p>
              <dl className="mt-3 grid grid-cols-2 gap-2 text-xs"><div><dt className="text-[var(--color-muted)]">{t("similarityMatchedWords")}</dt><dd className="font-semibold">{similarityRun.matched_word_count}</dd></div><div><dt className="text-[var(--color-muted)]">{t("similarityTargetWords")}</dt><dd className="font-semibold">{similarityRun.target_word_count}</dd></div><div><dt className="text-[var(--color-muted)]">{t("similarityExcludedWords")}</dt><dd className="font-semibold">{similarityRun.excluded_word_count}</dd></div><div><dt className="text-[var(--color-muted)]">{t("similarityCorpus")}</dt><dd className="font-semibold">{similarityRun.candidate_documents_scanned} / {similarityRun.candidate_documents_available}</dd></div></dl>
              <p className="mt-3 text-xs text-[var(--color-muted)]">{t("similarityMinimum", { count: similarityRun.minimum_match_words })}</p>
              {similarityRun.candidate_documents_scanned < similarityRun.candidate_documents_available && <p className="mt-2 text-xs text-amber-900">{t("similarityCorpusLimited")}</p>}
              {similarityRun.matches_truncated && <p className="mt-2 text-xs text-amber-900">{t("similarityMatchesTruncated")}</p>}
            </section>
            {similarityMatches.isLoading && <LoadingState label={t("similarityLoading")} />}
            {similarityMatches.isError && <ErrorState compact error={similarityMatches.error} onRetry={() => void similarityMatches.refetch()} />}
            {!similarityMatches.isLoading && !similarityMatches.isError && similarityRun.matches_count === 0 && <p className="rounded-xl bg-[var(--color-success-50)] p-3 text-sm font-semibold text-[var(--color-success-500)]">{t("similarityNoMatches")}</p>}
            {(similarityMatches.data ?? EMPTY_SIMILARITY_MATCHES).map((match) => <button key={match.id} type="button" onClick={() => focusSimilarity(match.id)} aria-pressed={selectedSimilarityMatch === match.id}
              className={`w-full rounded-xl border-l-4 border-amber-400 bg-amber-50 p-3 text-left ${selectedSimilarityMatch === match.id ? "ring-2 ring-[var(--color-brand-500)]" : ""}`}>
              <span className="text-xs font-bold uppercase tracking-wide">№{match.sequence} · {t("similarityMatchWords", { count: match.matched_word_count })}</span>
              <span className="mt-2 block text-xs font-semibold text-[var(--color-muted)]">{t("similarityTargetExcerpt")}</span><span className="mt-1 block text-sm">«{match.target_excerpt}»</span>
              {match.source_restricted ? <p className="mt-3 text-xs text-[var(--color-muted)]">{t("similaritySourceRestricted")}</p> : <><span className="mt-3 block text-xs font-semibold text-[var(--color-muted)]">{t("similaritySource", { name: match.source_label || match.source_filename || t("notSpecified") })}</span>{match.source_excerpt && <span className="mt-1 block text-sm">«{match.source_excerpt}»</span>}</>}
            </button>)}
          </>}
        </div>
        <div hidden={tab !== "remarks"} role="tabpanel" id="document-panel-remarks" aria-labelledby="document-tab-remarks" ref={findingsPanel} className="min-h-0 max-h-[55vh] space-y-3 overflow-y-auto p-3 lg:max-h-[calc(100vh-27rem)]">
          <label className="block text-xs font-medium">{t("runHistory")}<select className="input mt-1 w-full py-2" value={selectedRunId} onChange={event => { setSelectedRunId(event.target.value); setShowRunRules(false); }}>
            <option value="">{t("latestResult")}</option>{runs.data?.filter(job => job.status === "COMPLETED").map(job => <option key={job.id} value={job.id}>
              {t("runNumber", { number: job.run_number ?? 1 })} · {formatDateTime(job.queued_at)}
            </option>)}</select></label>
          {runs.isError && <ErrorState compact error={runs.error} onRetry={() => void runs.refetch()} />}
          {visibleResult && <button type="button" className="text-xs font-semibold underline" aria-expanded={showRunRules} onClick={() => setShowRunRules(value => !value)}>{t("usedRules")}</button>}
          {showRunRules && <section className="rounded-xl border border-[var(--color-border)] p-3">
            <h3 className="text-sm font-bold">{t("usedRules")}</h3>
            {runDetail.isLoading && <LoadingState label={t("settingsLoading")} />}
            {runDetail.isError && <ErrorState compact error={runDetail.error} onRetry={() => void runDetail.refetch()} />}
            {runDetail.data?.rules.map((rule, index) => <details key={index} className="mt-3"><summary className="text-xs font-semibold">{t(`ruleTypes.${rule.rule_type}`)} · {t(rule.enabled ? "enabled" : "ruleDisabled")}</summary>
              <RuleConfigFields type={rule.rule_type} config={rule.config} disabled patch={() => {}} /></details>)}
            {!!Object.keys(runDetail.data?.paragraph_overrides ?? {}).length && <ul className="mt-3 space-y-1 text-xs">{Object.entries(runDetail.data!.paragraph_overrides).map(([index, type]) => <li key={index}>{t("findingParagraph", { number: Number(index) })}: {t(`paragraphTypes.${type}`)}</li>)}</ul>}
          </section>}
          {(item.job.status === "QUEUED" || item.job.status === "PROCESSING") && <LoadingState label={t("analysisInProgress")} />}
          {item.job.status === "FAILED" && <p className="rounded-xl bg-[var(--color-danger-50)] p-3 text-sm text-[var(--color-danger-500)]">{t("teacherJobFailed")}</p>}
          {active && visibleResult && <p className="text-xs text-[var(--color-muted)]">{t("previousResultKept")}</p>}
          {summary?.rules_evaluated === 0 && summary.first_page_exclusion !== "BOUNDARY_UNKNOWN" && summary.first_page_exclusion !== "NO_CONTENT" && <p className="rounded-xl bg-[var(--color-danger-50)] p-3 text-sm font-semibold text-[var(--color-danger-500)]">{t("noRulesEvaluated")}</p>}
          {findings.isLoading && <LoadingState label={t("loadingFindings")} />}
          {findings.isError && <ErrorState compact error={findings.error} onRetry={() => void findings.refetch()} />}
          {summary && summary.rules_evaluated > 0 && summary.findings_count === 0 && <p className="rounded-xl bg-[var(--color-success-50)] p-3 text-sm font-semibold text-[var(--color-success-500)]">{t("noFindings")}</p>}
          {allFindings.slice(offset, offset + PAGE_SIZE).map((finding) => <button
            key={finding.id}
            type="button"
            data-finding-card={finding.id}
            aria-pressed={selectedFinding === finding.id}
            onClick={() => focusFinding(finding.id)}
            className={`w-full rounded-xl border-l-4 p-3 text-left transition-shadow hover:shadow-md ${severityClasses[finding.severity]} ${selectedFinding === finding.id ? "ring-2 ring-[var(--color-brand-500)]" : ""}`}
          >
            <span className="text-xs font-bold uppercase tracking-wide">№{finding.sequence} · {t(`severities.${finding.severity}` as never)}</span>
            <strong className="mt-1 block text-sm">{t(`findingCodes.${finding.code}` as never, { defaultValue: finding.code })}</strong>
            <span className="mt-1 block text-xs font-semibold">{t(`findingProperties.${finding.property_name}` as never, { defaultValue: t(`ruleTypes.${finding.rule_type}` as never) })}</span>
            {typeof finding.location.paragraph_type === "string" && <span className="mt-1 block text-xs">{t(`paragraphTypes.${finding.location.paragraph_type}` as never)}</span>}
            <span className="mt-2 block text-xs font-semibold text-[var(--color-brand-700)]">{locationText(finding)}</span>
            {positions[finding.id]?.excerpt && <span className="mt-2 block break-words text-xs text-[var(--color-ink-soft)]">«{positions[finding.id].excerpt}»</span>}
            <dl className="mt-2 grid grid-cols-2 gap-2 text-xs"><div><dt className="font-semibold">{t("expected")}</dt><dd>{formatMetric(finding.expected)}</dd></div><div><dt className="font-semibold">{t("actual")}</dt><dd>{formatMetric(finding.actual)}</dd></div></dl>
          </button>)}
          {allFindings.length > PAGE_SIZE && <PaginationControls pagination={{ offset, limit: PAGE_SIZE, total: allFindings.length, hasMore: offset + PAGE_SIZE < allFindings.length }} onPageChange={(next) => { setOffset(next); setSelectedFinding(null); }} isFetching={findings.isFetching} label={t("remarks")} />}
        </div>
      </aside>

      <section className="card min-w-0 overflow-hidden">
        <div className="flex items-center gap-3 border-b border-[var(--color-border)] px-5 py-4"><DocumentTextIcon className="size-5 text-[var(--color-brand-600)]" /><div><h2 className="font-display font-bold">{t("documentPreview")}</h2><p className="text-xs text-[var(--color-muted)]">{t("previewHint")}</p></div></div>
        {preview.isLoading && <div className="p-5"><LoadingState label={t("loadingPreview")} /></div>}
        {preview.isError && <div className="p-5"><ErrorState error={preview.error} onRetry={() => void preview.refetch()} /></div>}
        {tab === "rules" && <p className="border-b border-[var(--color-border)] bg-[var(--color-brand-50)] px-5 py-3 text-sm">{t("paragraphSelectionHint")}</p>}
        {preview.data && !originalUnavailable && <PaginatedDocument preview={preview.data} findings={tab === "similarity" ? similarityMarkers : allFindings} selectedId={tab === "similarity" ? selectedSimilarityMatch : selectedFinding} onSelect={tab === "similarity" ? focusSimilarity : focusFinding} onPositions={setPositions} excludeFirstPage={summary?.first_page_exclusion === "APPLIED" || summary?.first_page_exclusion === "NO_CONTENT"}
          paragraphTypes={paragraphTypes} selectedParagraphIndex={selectedParagraph?.index} paragraphSelectionEnabled={tab === "rules"} onParagraphSelect={setSelectedParagraph} />}
      </section>
    </div>
  </div>;
}
