import { useMutation } from "@tanstack/react-query";
import { ArrowDownTrayIcon, ArrowPathIcon } from "@heroicons/react/24/outline";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ErrorState, LoadingState } from "../../components/ui/StateViews";
import { PaginationControls } from "../../components/ui/PaginationControls";
import { useLocaleFormatters } from "../../i18n/formatters";
import { TeacherDocumentUpload } from "./TeacherDocumentUpload";
import {
  downloadTeacherSubmissionOriginal,
  useTeacherDocumentSubmissions,
} from "./submissionApi";
import { SubmissionResult } from "./SubmissionResult";
import { DocumentChecksGate } from "./DocumentChecksGate";

export function TeacherDocumentChecksPage() {
  return <DocumentChecksGate><TeacherDocumentChecks /></DocumentChecksGate>;
}

function TeacherDocumentChecks() {
  const { t } = useTranslation(["documentChecks", "common"]);
  const { formatDateTime, formatFileSize } = useLocaleFormatters();
  const [params, setParams] = useSearchParams();
  const offset = Math.max(0, Number(params.get("offset") ?? 0) || 0);
  const archived = params.get("archived") === "true";
  const submissions = useTeacherDocumentSubmissions(offset, archived);
  const download = useMutation({ mutationFn: downloadTeacherSubmissionOriginal });

  const changePage = (nextOffset: number) => {
    const next = new URLSearchParams(params);
    if (nextOffset) next.set("offset", String(nextOffset));
    else next.delete("offset");
    setParams(next);
  };
  const changeArchive = (next: boolean) => {
    const value = new URLSearchParams(params);
    value.delete("offset");
    if (next) value.set("archived", "true"); else value.delete("archived");
    setParams(value);
  };

  return (
    <div>
      <header className="mb-7 border-b border-[var(--color-border)] pb-6">
        <p className="page-kicker">{t("teacherOnly")}</p>
        <h1 className="page-title mt-1">{t("directChecks")}</h1>
        <p className="page-description">{t("directChecksDescription")}</p>
      </header>

      <TeacherDocumentUpload />

      <section className="section-panel overflow-hidden" aria-labelledby="history-heading">
        <div className="section-heading flex flex-wrap items-center justify-between gap-3">
          <div><h2 id="history-heading" className="font-bold text-[var(--color-ink)]">{t("checkHistory")}</h2><p className="mt-0.5 text-sm text-[var(--color-muted)]">{t("checkHistoryDescription")}</p></div>
          <div className="flex gap-2"><button type="button" className={`btn px-3 py-2 ${!archived ? "btn-primary" : "btn-secondary"}`} onClick={() => changeArchive(false)}>{t("checkHistory")}</button><button type="button" className={`btn px-3 py-2 ${archived ? "btn-primary" : "btn-secondary"}`} onClick={() => changeArchive(true)}>{t("archivedDocument", { defaultValue: "Archived" })}</button><button type="button" className="btn btn-ghost px-3 py-2" onClick={() => void submissions.refetch()}><ArrowPathIcon className="size-4" />{t("refreshHistory")}</button></div>
        </div>
        {submissions.isLoading && <LoadingState label={t("loadingChecks")} />}
        {submissions.isError && <ErrorState error={submissions.error} onRetry={() => void submissions.refetch()} />}
        {download.isError && <ErrorState compact error={download.error} />}
        {submissions.data && !submissions.data.items.length && <p className="p-5 text-sm text-[var(--color-muted)]">{t("noChecks")}</p>}
        {!!submissions.data?.items.length && (
          <div className="overflow-x-auto">
            <table className="table-base responsive-table">
              <thead><tr><th className="px-5 py-3">{t("studentLabel")}</th><th className="px-5 py-3">{t("originalDocument")}</th><th className="px-5 py-3">{t("submittedAt")}</th><th className="px-5 py-3">{t("jobStatus")}</th><th className="px-5 py-3">{t("checkFindings")}</th><th className="px-5 py-3">{t("original")}</th></tr></thead>
              <tbody>{submissions.data.items.map((submission) => (
                <tr key={submission.id}>
                  <td data-label={t("studentLabel")} className="px-5 py-4 text-[var(--color-ink-soft)]">{submission.student_label || t("notSpecified")}</td>
                  <td data-label={t("originalDocument")} className="max-w-xs px-5 py-4"><p className="break-words font-semibold text-[var(--color-ink)]">{submission.original_filename}</p><p className="mt-1 text-xs text-[var(--color-muted)]">{submission.lifecycle?.original_deleted_at ? t("originalRemoved") : formatFileSize(submission.size_bytes)}{submission.lifecycle?.original_delete_requested_at && !submission.lifecycle.original_deleted_at ? ` · ${t("originalRemovalPending")}` : ""}</p></td>
                  <td data-label={t("submittedAt")} className="px-5 py-4 text-[var(--color-ink-soft)]"><time dateTime={submission.submitted_at}>{formatDateTime(submission.submitted_at)}</time></td>
                  <td data-label={t("jobStatus")} className="px-5 py-4"><span className={`inline-flex rounded-[5px] border px-2 py-1 text-xs font-semibold ${submission.job.status === "FAILED" ? "border-[var(--color-danger-500)]/20 bg-[var(--color-danger-50)] text-[var(--color-danger-500)]" : submission.job.status === "COMPLETED" ? "border-[var(--color-success-500)]/20 bg-[var(--color-success-50)] text-[var(--color-success-500)]" : "border-amber-500/20 bg-[var(--color-amber-50)] text-[var(--color-amber-500)]"}`}>{t(`jobStatuses.${submission.job.status}`)}</span>{submission.job.status === "FAILED" && <p className="mt-1 text-sm text-[var(--color-danger-500)]">{t("teacherJobFailed")}</p>}</td>
                  <td data-label={t("checkFindings")} className="px-5 py-4 align-top"><SubmissionResult submission={submission} /></td>
                  <td data-label={t("original")} className="px-5 py-4"><button type="button" className="btn btn-secondary px-3 py-2" disabled={download.isPending || !!submission.lifecycle?.original_delete_requested_at} onClick={() => download.mutate(submission)}><ArrowDownTrayIcon className="size-4" />{t("downloadOriginal")}</button></td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
        {submissions.data && <div className="border-t border-[var(--color-border)] p-4"><PaginationControls pagination={submissions.data} onPageChange={changePage} isFetching={submissions.isFetching} label={t("checkHistory")} /></div>}
      </section>
    </div>
  );
}
