import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { api } from "../../lib/api";
import { fetchPage } from "../../lib/pagination";
import { ErrorState, LoadingState } from "../../components/ui/StateViews";
import { PaginationControls } from "../../components/ui/PaginationControls";
import { useLocaleFormatters } from "../../i18n/formatters";
import { isLocale } from "../../i18n/types";
import { reportBase, reportPayload, type GroupReport, type GroupReportItem, type ReportContent, type ReportFinding } from "./groupReportApi";

function toggle<T>(items: T[], item: T): T[] { return items.includes(item) ? items.filter(value => value !== item) : [...items, item]; }

export function GroupReportPanel({ groupId, includedWorks }: { groupId: string; includedWorks: number }) {
  const { t, i18n } = useTranslation("documentChecks");
  const { formatDateTime } = useLocaleFormatters();
  const client = useQueryClient();
  const [offset, setOffset] = useState(0);
  const [report, setReport] = useState<GroupReport | null>(null);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const requestId = useRef(crypto.randomUUID());
  const [error, setError] = useState<unknown>(null);
  const base = reportBase(groupId);
  const history = useQuery({ queryKey: ["group-reports", groupId, offset], queryFn: () => fetchPage<GroupReportItem>(base, { offset }) });
  async function open(id?: string) {
    if (busyRef.current) return;
    busyRef.current = true; setBusy(true); setError(null);
    try {
      const locale = isLocale(i18n.resolvedLanguage) ? i18n.resolvedLanguage : "ru";
      const response = id ? await api.get<GroupReport>(`${base}/${id}`) : await api.post<GroupReport>(base, { request_id: requestId.current, locale });
      setReport(response.data);
      if (!id) requestId.current = crypto.randomUUID();
      void client.invalidateQueries({ queryKey: ["group-reports", groupId] });
    } catch (failure) { setError(failure); }
    finally { busyRef.current = false; setBusy(false); }
  }
  return <section className="section-panel mb-5 space-y-4 p-5" aria-label={t("groupReport.history")}>
    <button className="btn btn-primary" disabled={busy || includedWorks === 0 || !!report} onClick={() => void open()}>{t("groupReport.create")}</button>
    {includedWorks === 0 && <p className="text-sm text-[var(--color-muted)]">{t("groupReport.unavailable")}</p>}
    {busy && <LoadingState label={t("groupReport.loading")} />}
    {error != null && <ErrorState compact error={error} />}
    {report && <ReportEditor key={report.id} initial={report} onClose={() => setReport(null)} onSaved={value => {
      setReport(value); void client.invalidateQueries({ queryKey: ["group-reports", groupId] });
    }} />}
    <h2 className="font-bold">{t("groupReport.history")}</h2>
    {history.isLoading && <LoadingState label={t("groupReport.loading")} />}
    {history.isError && <ErrorState compact error={history.error} onRetry={() => void history.refetch()} />}
    {history.data && <>
      {!history.data.items.length && <p className="text-sm">{t("groupReport.empty")}</p>}
      <ul className="space-y-3">{history.data.items.map(item => <li key={item.id} className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--color-border)] pt-3">
        <div className="min-w-0 flex-1"><p className="break-words font-semibold">{item.title}</p><p className="text-xs text-[var(--color-muted)]">{formatDateTime(item.created_at)} · {item.locale.toUpperCase()} · {t(item.generated_at ? "groupReport.generated" : "groupReport.draft")}</p></div>
        <button className="btn btn-secondary" disabled={busy || !!report} onClick={() => void open(item.id)}>{t("groupReport.open")}</button>
      </li>)}</ul>
      <PaginationControls pagination={history.data} onPageChange={setOffset} isFetching={history.isFetching} label={t("groupReport.history")} />
    </>}
  </section>;
}

function ReportEditor({ initial, onClose, onSaved }: { initial: GroupReport; onClose: () => void; onSaved: (report: GroupReport) => void }) {
  const { t } = useTranslation("documentChecks", { lng: initial.locale });
  const { formatDateTime } = useLocaleFormatters();
  const [report, setReport] = useState(initial);
  const [content, setContent] = useState<ReportContent>(initial.content);
  const [preview, setPreview] = useState(!!initial.generated_at);
  const [busy, setBusy] = useState<"save" | "export" | "reload" | null>(null);
  const busyRef = useRef(false);
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState(true);
  const base = `${reportBase(report.group_id)}/${report.id}`;
  function change(patch: Partial<ReportContent>) { setContent(current => ({ ...current, ...patch })); setSaved(false); }
  async function save(showPreview: boolean) {
    if (busyRef.current) return;
    busyRef.current = true; setBusy("save"); setError(null);
    try {
      const response = await api.put<GroupReport>(base, reportPayload(report, content));
      setReport(response.data); setContent(response.data.content); onSaved(response.data); setSaved(true); setPreview(showPreview);
    } catch (failure) { setError(failure); }
    finally { busyRef.current = false; setBusy(null); }
  }
  async function reload() {
    if (busyRef.current) return;
    busyRef.current = true; setBusy("reload");
    try {
      const response = await api.get<GroupReport>(base);
      setReport(response.data); setContent(response.data.content); setSaved(true); setPreview(!!response.data.generated_at); setError(null);
    } catch (failure) { setError(failure); }
    finally { busyRef.current = false; setBusy(null); }
  }
  async function download() {
    if (busyRef.current) return;
    busyRef.current = true; setBusy("export"); setError(null);
    try {
      if (!report.generated_at) {
        const response = await api.post<GroupReport>(`${base}/export`, { revision: report.revision });
        setReport(response.data); onSaved(response.data);
      }
      const response = await api.get<Blob>(`${base}/download`, { responseType: "blob" });
      const url = URL.createObjectURL(response.data);
      try {
        const link = document.createElement("a"); link.href = url; link.download = `group-report-${report.id}.pptx`;
        document.body.appendChild(link); link.click(); link.remove();
      } finally { URL.revokeObjectURL(url); }
    } catch (failure) { setError(failure); }
    finally { busyRef.current = false; setBusy(null); }
  }
  return <div className="space-y-4 border-t border-[var(--color-border)] pt-5">
    <p className="text-xs text-[var(--color-muted)]">{t("groupReport.snapshot", { date: formatDateTime(report.snapshot.captured_at), locale: report.locale.toUpperCase() })}</p>
    <ReportCoverage report={report} />
    <p className="text-sm">{t("groupReport.privacy")}</p>
    {report.generated_at && <p className="text-sm font-semibold">{t("groupReport.frozen")}</p>}
    {preview ? <ContentPreview report={report} /> : <form className="space-y-5" onSubmit={event => { event.preventDefault(); void save(false); }}>
      <fieldset disabled={!!busy} className="space-y-4">
        <label className="block text-sm font-semibold">{t("groupReport.title")}<input className="input mt-1 w-full" required maxLength={500} value={content.title} onChange={event => change({ title: event.target.value })} /></label>
        <label className="block text-sm font-semibold">{t("groupReport.introduction")}<textarea className="input mt-1 w-full" rows={3} maxLength={10000} value={content.introduction} onChange={event => change({ introduction: event.target.value })} /></label>
        <fieldset className="space-y-2"><legend className="font-bold">{t("groupReport.types")}</legend>
          {report.snapshot.summary.violations.length ? report.snapshot.summary.violations.map(row => <label className="flex items-start gap-2 text-sm" key={row.rule_type}>
            <input type="checkbox" checked={content.selected_rule_types.includes(row.rule_type)} onChange={() => change({ selected_rule_types: toggle(content.selected_rule_types, row.rule_type) })} />
            {t(`ruleTypes.${row.rule_type}`)} · {row.violations_count} {t("reviewGroups.violations")} · {row.works_count} {t("reviewGroups.affectedWorks")}
          </label>) : <p className="text-sm">{t("reviewGroups.noViolations")}</p>}
        </fieldset>
        <ExampleSelector report={report} selected={content.finding_ids} onChange={finding_ids => change({ finding_ids })} />
        <fieldset className="space-y-2"><legend className="font-bold">{t("groupReport.remarks")}</legend>
          <p className="text-sm text-[var(--color-muted)]">{t("groupReport.remarksHint")}</p>
          {report.snapshot.remarks.map((remark, index) => <label className="flex items-start gap-2" key={remark.submission_id}>
            <input type="checkbox" checked={content.remark_submission_ids.includes(remark.submission_id)} disabled={!content.remark_submission_ids.includes(remark.submission_id) && content.remark_submission_ids.length >= 30}
              onChange={() => change({ remark_submission_ids: toggle(content.remark_submission_ids, remark.submission_id) })} />
            <span className="min-w-0 whitespace-pre-wrap break-words text-sm">{t("groupReport.remark", { number: index + 1 })}: {remark.text}</span>
          </label>)}
          {!report.snapshot.remarks.length && <p className="text-sm">{t("groupReport.noRemarks")}</p>}
        </fieldset>
        <label className="block text-sm font-semibold">{t("groupReport.conclusions")}<textarea className="input mt-1 w-full" rows={5} maxLength={20000} value={content.conclusions} onChange={event => change({ conclusions: event.target.value })} /></label>
      </fieldset>
      <div className="flex flex-wrap gap-3"><button className="btn btn-secondary" disabled={!!busy}>{t(busy === "save" ? "groupReport.saving" : "groupReport.save")}</button>
        <button type="button" className="btn btn-primary" disabled={!!busy || !content.title.trim()} onClick={() => void save(true)}>{t("groupReport.preview")}</button></div>
    </form>}
    {preview && <div className="flex flex-wrap gap-3">
      {!report.generated_at && <button className="btn btn-secondary" disabled={!!busy} onClick={() => setPreview(false)}>{t("groupReport.edit")}</button>}
      <button className="btn btn-primary" disabled={!!busy} onClick={() => void download()}>{t(busy === "export" ? "groupReport.generating" : report.generated_at ? "groupReport.redownload" : "groupReport.download")}</button>
    </div>}
    {saved && <p role="status" className="text-xs text-[var(--color-muted)]">{t("groupReport.saved", { revision: report.revision })}</p>}
    {error != null && <><ErrorState compact error={error} /><button className="btn btn-secondary" disabled={!!busy} onClick={() => void reload()}>{t("groupReport.reload")}</button></>}
    <button className="btn btn-secondary" disabled={!!busy} onClick={onClose}>{t("groupReport.close")}</button>
  </div>;
}

function ReportCoverage({ report }: { report: GroupReport }) {
  const { t } = useTranslation("documentChecks", { lng: report.locale });
  const summary = report.snapshot.summary;
  return <div className="space-y-2 text-sm">
    <p className="font-bold">{t("groupReport.included", { count: summary.included_works })}</p>
    {summary.reviewed_works < summary.total_works && <p className="text-amber-900">{t("groupReport.partial", { reviewed: summary.reviewed_works, total: summary.total_works, included: summary.included_works })}</p>}
    {summary.included_works < summary.reviewed_works && <p className="text-amber-900">{t("groupReport.missing", { included: summary.included_works, reviewed: summary.reviewed_works })}</p>}
    {!!summary.truncated_works && <p className="text-amber-900">{t("groupReport.truncated", { count: summary.truncated_works })}</p>}
    {!!report.snapshot.skipped_works && <p className="text-amber-900">{t("groupReport.skipped", { count: report.snapshot.skipped_works })}</p>}
    <p className="text-[var(--color-muted)]">{t("groupReport.limits")}</p>
  </div>;
}

function FindingContent({ finding, locale }: { finding: ReportFinding; locale: string }) {
  const { t } = useTranslation("documentChecks", { lng: locale });
  function metric(value: Record<string, unknown>) {
    const scalar = (item: unknown): string => {
      if (item == null) return t("groupReport.unknown");
      if (typeof item === "boolean") return t(item ? "ruleValues.YES" : "ruleValues.NO");
      if (typeof item === "string" && ["LEFT", "CENTER", "RIGHT", "JUSTIFY", "PORTRAIT", "LANDSCAPE", "CUSTOM", "UNKNOWN"].includes(item)) return t(`ruleValues.${item}` as never);
      return String(item);
    };
    const unit = value.unit === "mm" ? t("unitMm") : value.unit === "pt" ? t("unitPt") : value.unit === "multiple" ? t("unitMultiple") : value.unit ?? "";
    if (Array.isArray(value.allowed)) return value.allowed.map(scalar).join(", ") || t("groupReport.unknown");
    if ("width_mm" in value || "height_mm" in value) return `${scalar(value.width_mm)} × ${scalar(value.height_mm)} ${t("unitMm")}`;
    if ("min" in value || "max" in value) return `${scalar(value.min)}–${scalar(value.max)} ${unit}`.trim();
    if ("value" in value) return `${scalar(value.value)} ${unit}`.trim();
    return t("groupReport.unknown");
  }
  const parts = Object.entries(finding.location).map(([key, value]) => {
    const translation = key === "paragraph_index" ? "findingParagraph" : key === "section_index" ? "findingSection" : key === "run_index" ? "findingRun" : null;
    return translation ? t(translation, { number: value }) : `${t(key === "table_index" ? "groupReport.locationNames.table_index" : "groupReport.locationNames.page")}: ${value}`;
  });
  return <div className="min-w-0 space-y-1 break-words text-sm"><p className="font-bold">{t(`ruleTypes.${finding.rule_type}`)}</p>
    <p>{t("groupReport.location")}: {parts.join(", ") || t("groupReport.unknown")}</p>
    <p>{t("groupReport.actual")}: {metric(finding.actual)}</p><p>{t("groupReport.expected")}: {metric(finding.expected)}</p></div>;
}

function ExampleSelector({ report, selected, onChange }: { report: GroupReport; selected: string[]; onChange: (ids: string[]) => void }) {
  const { t } = useTranslation("documentChecks", { lng: report.locale });
  const [offset, setOffset] = useState(0);
  const [ruleType, setRuleType] = useState("");
  const findings = useQuery({ queryKey: ["report-findings", report.id, ruleType, offset],
    queryFn: () => fetchPage<ReportFinding>(`${reportBase(report.group_id)}/${report.id}/findings${ruleType ? `?rule_type=${ruleType}` : ""}`, { offset }) });
  return <fieldset className="space-y-3"><legend className="font-bold">{t("groupReport.chooseExamples")}</legend>
    <p className="text-sm">{t("groupReport.limit")} ({selected.length}/30)</p>
    <label className="text-sm">{t("groupReport.filter")}<select className="input ml-2" value={ruleType} onChange={event => { setRuleType(event.target.value); setOffset(0); }}>
      <option value="">{t("groupReport.all")}</option>{report.snapshot.summary.violations.map(row => <option value={row.rule_type} key={row.rule_type}>{t(`ruleTypes.${row.rule_type}`)}</option>)}</select></label>
    {findings.isLoading && <LoadingState label={t("groupReport.loading")} />}
    {findings.isError && <ErrorState compact error={findings.error} onRetry={() => void findings.refetch()} />}
    {findings.data && <>
      {findings.data.items.map((finding, index) => <label className="flex items-start gap-3 border-t border-[var(--color-border)] pt-3" key={finding.id}>
        <input aria-label={t("groupReport.example", { number: offset + index + 1 })} type="checkbox" checked={selected.includes(finding.id)}
          disabled={!selected.includes(finding.id) && selected.length >= 30} onChange={() => onChange(toggle(selected, finding.id))} />
        <FindingContent finding={finding} locale={report.locale} />
      </label>)}
      <PaginationControls pagination={findings.data} onPageChange={setOffset} isFetching={findings.isFetching} label={t("groupReport.examples")} />
    </>}
  </fieldset>;
}

function ContentPreview({ report }: { report: GroupReport }) {
  const { t } = useTranslation("documentChecks", { lng: report.locale });
  const content = report.content;
  const summary = report.snapshot.summary;
  const rows = summary.violations.filter(row => content.selected_rule_types.includes(row.rule_type));
  return <article aria-label={t("groupReport.preview")} className="space-y-5">
    <p className="text-sm text-[var(--color-muted)]">{t("groupReport.previewHint")}</p>
    <h2 className="whitespace-pre-wrap break-words text-xl font-bold">{content.title}</h2><p className="break-words">{report.snapshot.group_name} · {report.snapshot.captured_at.slice(0, 10)}</p>
    <h3 className="font-bold">{t("groupReport.scope")}</h3>
    <dl>{([["reviewGroups.total", summary.total_works], ["reviewGroups.completed", summary.reviewed_works], ["reviewGroups.pending", summary.pending_works], ["groupReport.included", summary.included_works]] as const)
      .map(([label, count]) => <div className="flex gap-3" key={label}><dt>{t(label, { count })}</dt><dd>{count}</dd></div>)}</dl>
    <h3 className="font-bold">{t("groupReport.introduction")}</h3><p className="whitespace-pre-wrap break-words">{content.introduction || t("groupReport.noText")}</p>
    <h3 className="font-bold">{t("groupReport.problems")}</h3>
    {rows.map(row => <div className="space-y-1" key={row.rule_type}><p className="text-sm">{t(`ruleTypes.${row.rule_type}`)}: {row.works_count}</p><div className="h-3 rounded bg-[var(--color-surface)]"><div className="h-3 rounded bg-[var(--color-brand-600)]" style={{ width: `${row.works_count / Math.max(1, summary.included_works) * 100}%` }} /></div></div>)}
    {!rows.length && <p>{t(summary.violations.length ? "groupReport.noTypes" : "reviewGroups.noViolations")}</p>}
    {rows.length > 0 && <div className="overflow-x-auto"><table className="table-base"><caption className="text-left font-bold">{t("reviewGroups.summary")}</caption><thead><tr>
      <th className="p-3">{t("reviewGroups.violationType")}</th><th className="p-3">{t("reviewGroups.violations")}</th><th className="p-3">{t("reviewGroups.affectedWorks")}</th>
    </tr></thead><tbody>{rows.map(row => <tr key={row.rule_type}><td className="p-3">{t(`ruleTypes.${row.rule_type}`)}</td><td className="p-3">{row.violations_count}</td><td className="p-3">{row.works_count}</td></tr>)}</tbody></table></div>}
    <h3 className="font-bold">{t("groupReport.examples")}</h3>{content.examples.map((finding, index) => <div key={finding.id}><p className="font-semibold">{t("groupReport.example", { number: index + 1 })}</p><FindingContent finding={finding} locale={report.locale} /></div>)}
    {!content.examples.length && <p>{t("groupReport.noExamples")}</p>}
    {content.remarks.length > 0 && <><h3 className="font-bold">{t("groupReport.remarks")}</h3>{content.remarks.map((remark, index) => <p className="whitespace-pre-wrap break-words" key={index}>{remark}</p>)}</>}
    <h3 className="font-bold">{t("groupReport.conclusions")}</h3><p className="whitespace-pre-wrap break-words">{content.conclusions || t("groupReport.noText")}</p>
  </article>;
}
