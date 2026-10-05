import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useState } from "react";
import { ErrorState, LoadingState } from "../../components/ui/StateViews";
import { PaginationControls } from "../../components/ui/PaginationControls";
import { useLocaleFormatters } from "../../i18n/formatters";
import { DocumentChecksGate } from "./DocumentChecksGate";
import { TeacherDocumentUpload } from "./TeacherDocumentUpload";
import { useGroupSummary, useGroupWorks, useReviewGroup, useReviewGroups, useSaveReviewGroup, type ReviewGroup } from "./reviewGroupApi";

function GroupForm({ group, onSaved }: { group?: ReviewGroup; onSaved?: (group: ReviewGroup) => void }) {
  const { t } = useTranslation(["documentChecks", "common"]);
  const save = useSaveReviewGroup(group?.id);
  return <form className="section-panel mb-5 space-y-3 p-5" onSubmit={event => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    save.mutate({ name: String(data.get("name")).trim(), description: String(data.get("description")).trim() || null }, { onSuccess: onSaved });
  }}>
    <h2 className="font-bold">{t(group ? "reviewGroups.edit" : "reviewGroups.create")}</h2>
    <label className="block text-sm font-semibold">{t("reviewGroups.name")}<input className="input mt-1 w-full" name="name" required maxLength={255} defaultValue={group?.name} /></label>
    <label className="block text-sm font-semibold">{t("reviewGroups.description")}<textarea className="input mt-1 w-full" name="description" maxLength={5000} defaultValue={group?.description ?? ""} /></label>
    {save.isError && <ErrorState compact error={save.error} />}
    <button className="btn btn-primary" disabled={save.isPending}>{t(group ? "common:save" : "common:create")}</button>
  </form>;
}

function offsetOf(params: URLSearchParams) {
  const value = Number(params.get("offset"));
  return Number.isSafeInteger(value) && value > 0 ? value : 0;
}

export function ReviewGroupsPage() { return <DocumentChecksGate><ReviewGroups /></DocumentChecksGate>; }
function ReviewGroups() {
  const { t } = useTranslation("documentChecks");
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const groups = useReviewGroups(offsetOf(params));
  return <div>
    <header className="mb-6"><h1 className="page-title">{t("reviewGroups.title")}</h1><p className="page-description">{t("reviewGroups.descriptionHint")}</p></header>
    <GroupForm onSaved={group => navigate(`/review-groups/${group.id}`)} />
    {groups.isLoading && <LoadingState label={t("loadingChecks")} />}
    {groups.isError && <ErrorState error={groups.error} onRetry={() => void groups.refetch()} />}
    {groups.data && <section className="section-panel overflow-hidden">
      {!groups.data.items.length && <p className="p-5">{t("reviewGroups.empty")}</p>}
      <ul>{groups.data.items.map(group => <li className="border-b border-[var(--color-border)] p-5" key={group.id}>
        <Link className="font-bold text-[var(--color-brand-700)]" to={`/review-groups/${group.id}`}>{group.name}</Link>
        {group.description && <p className="mt-1 whitespace-pre-wrap break-words text-sm text-[var(--color-muted)]">{group.description}</p>}
      </li>)}</ul>
      <div className="p-4"><PaginationControls pagination={groups.data} onPageChange={offset => setParams({ offset: String(offset) })} isFetching={groups.isFetching} label={t("reviewGroups.title")} /></div>
    </section>}
  </div>;
}

export function ReviewGroupPage() {
  const { groupId = "" } = useParams();
  return <DocumentChecksGate><ReviewGroupDetail key={groupId} id={groupId} /></DocumentChecksGate>;
}
function ReviewGroupDetail({ id }: { id: string }) {
  const { t } = useTranslation("documentChecks");
  const { formatDateTime, formatNumber } = useLocaleFormatters();
  const [params, setParams] = useSearchParams();
  const status = ["pending", "completed"].includes(params.get("review_status") ?? "") ? params.get("review_status")! : "";
  const group = useReviewGroup(id);
  const works = useGroupWorks(id, offsetOf(params), status);
  const summary = useGroupSummary(id);
  const [editing, setEditing] = useState(false);
  if (group.isLoading) return <LoadingState label={t("loadingChecks")} />;
  if (!group.data) return <ErrorState error={group.error} onRetry={() => void group.refetch()} />;
  return <div>
    <Link className="text-sm font-semibold text-[var(--color-brand-700)]" to="/review-groups">{t("reviewGroups.back")}</Link>
    <header className="my-5 flex flex-wrap items-start justify-between gap-3"><div><h1 className="page-title">{group.data.name}</h1><p className="page-description whitespace-pre-wrap break-words">{group.data.description}</p></div>
      <button className="btn btn-secondary" onClick={() => setEditing(!editing)}>{t("reviewGroups.edit")}</button></header>
    {editing && <GroupForm group={group.data} onSaved={() => setEditing(false)} />}
    {summary.isLoading && <LoadingState label={t("reviewGroups.summary")} />}
    {summary.isError && <ErrorState error={summary.error} onRetry={() => void summary.refetch()} />}
    {summary.data && <>
      <dl className="mb-5 grid gap-3 sm:grid-cols-3">{([
        ["reviewGroups.total", summary.data.total_works], ["reviewGroups.pending", summary.data.pending_works], ["reviewGroups.completed", summary.data.reviewed_works],
      ] as const).map(([label, count]) => <div className="section-panel p-5" key={label}><dt className="text-sm text-[var(--color-muted)]">{t(label)}</dt><dd className="mt-2 text-3xl font-bold">{formatNumber(count)}</dd></div>)}</dl>
      <section className="section-panel mb-5 overflow-hidden" aria-labelledby="group-summary-heading">
        <div className="section-heading"><h2 id="group-summary-heading" className="font-bold">{t("reviewGroups.summary")}</h2><p className="mt-1 text-sm text-[var(--color-muted)]">{t("reviewGroups.summaryHint", { count: summary.data.included_works })}</p></div>
        {!!summary.data.truncated_works && <p className="p-4 text-sm text-amber-900">{t("reviewGroups.truncated", { count: summary.data.truncated_works })}</p>}
        {summary.data.violations.length ? <div className="overflow-x-auto"><table className="table-base"><thead><tr><th className="p-4">{t("reviewGroups.violationType")}</th><th className="p-4">{t("reviewGroups.violations")}</th><th className="p-4">{t("reviewGroups.affectedWorks")}</th></tr></thead>
          <tbody>{summary.data.violations.map(row => <tr key={row.rule_type}><td className="p-4">{t(`ruleTypes.${row.rule_type}`)}</td><td className="p-4">{formatNumber(row.violations_count)}</td><td className="p-4">{formatNumber(row.works_count)}</td></tr>)}</tbody></table></div>
          : <p className="p-5 text-sm">{t(summary.data.included_works ? "reviewGroups.noViolations" : "reviewGroups.noReviewedWorks")}</p>}
      </section>
    </>}
    <TeacherDocumentUpload groupId={id} />
    <section className="section-panel overflow-hidden">
      <div className="section-heading flex flex-wrap items-center justify-between gap-3"><h2 className="font-bold">{t("reviewGroups.works")}</h2>
        <label className="text-sm">{t("reviewGroups.filter")}<select className="input ml-2" value={status} onChange={event => setParams({ review_status: event.target.value })}>
          <option value="">{t("reviewGroups.all")}</option><option value="pending">{t("reviewGroups.pending")}</option><option value="completed">{t("reviewGroups.completed")}</option>
        </select></label></div>
      <p className="px-5 py-3 text-xs text-[var(--color-muted)]">{t("reviewGroups.worksHint")}</p>
      {works.isLoading && <LoadingState label={t("loadingChecks")} />}
      {works.isError && <ErrorState error={works.error} onRetry={() => void works.refetch()} />}
      {works.data && <>
        {!works.data.items.length ? <p className="p-5">{t(status ? "reviewGroups.noMatches" : "reviewGroups.noWorks")}</p> : <div className="overflow-x-auto"><table className="table-base responsive-table">
          <thead><tr>{["reviewGroups.student", "reviewGroups.workTitle", "reviewGroups.workType", "submittedAt", "reviewGroups.automaticStatus", "reviewGroups.teacherReview", "reviewGroups.violations", "reviewGroups.open"].map(key => <th className="px-4 py-3" key={key}>{t(key as never)}</th>)}</tr></thead>
          <tbody>{works.data.items.map(work => <tr key={work.id}>
            <td data-label={t("reviewGroups.student")} className="p-4">{work.student_label}</td>
            <td data-label={t("reviewGroups.workTitle")} className="p-4 font-semibold">{work.work_title}</td>
            <td data-label={t("reviewGroups.workType")} className="p-4">{t(work.work_type === "COURSEWORK" ? "reviewGroups.coursework" : "reviewGroups.report")}</td>
            <td data-label={t("submittedAt")} className="p-4">{formatDateTime(work.submitted_at)}</td>
            <td data-label={t("reviewGroups.automaticStatus")} className="p-4">{t(`jobStatuses.${work.job.status}`)}</td>
            <td data-label={t("reviewGroups.teacherReview")} className="p-4">{t(work.teacher_review?.completed_at ? "reviewGroups.completed" : "reviewGroups.pending")}</td>
            <td data-label={t("reviewGroups.violations")} className="p-4">{work.job.status === "COMPLETED" ? work.job.result_summary?.findings_count ?? "—" : "—"}{work.job.result_summary?.findings_truncated ? "+" : ""}</td>
            <td data-label={t("reviewGroups.open")} className="p-4"><Link className="btn btn-secondary whitespace-nowrap" to={`/document-checks/${work.id}`}>{t("reviewGroups.open")}</Link></td>
          </tr>)}</tbody></table></div>}
        <div className="border-t border-[var(--color-border)] p-4"><PaginationControls pagination={works.data} onPageChange={offset => setParams({ review_status: status, offset: String(offset) })} isFetching={works.isFetching} label={t("reviewGroups.works")} /></div>
      </>}
    </section>
  </div>;
}
