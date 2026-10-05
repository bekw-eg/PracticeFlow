import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { ErrorState } from "../../components/ui/StateViews";
import { useLocaleFormatters } from "../../i18n/formatters";
import type { DocumentCheckJob, TeacherDocumentSubmission } from "../../types/api";
import { useSaveTeacherReview } from "./reviewGroupApi";

export function TeacherReviewPanel({ submission, viewedJob, ready, onShowReviewedRun }: {
  submission: TeacherDocumentSubmission; viewedJob?: DocumentCheckJob; ready: boolean; onShowReviewedRun: (id: string) => void;
}) {
  const { t } = useTranslation("documentChecks");
  const { formatDateTime } = useLocaleFormatters();
  const saved = submission.teacher_review;
  const [draft, setDraft] = useState<{ remarks: string; revision: number } | null>(null);
  const save = useSaveTeacherReview(submission.id);
  const client = useQueryClient();
  const reload = useMutation({ mutationFn: () => client.fetchQuery({
    queryKey: ["teacher-document-submission", submission.id],
    queryFn: async () => (await api.get<TeacherDocumentSubmission>(`/document-checks/teacher/submissions/${submission.id}`)).data,
    staleTime: 0,
  }), onSuccess: () => { setDraft(null); save.reset(); } });
  const busy = save.isPending || reload.isPending;
  const value = draft ?? { remarks: saved?.remarks ?? "", revision: saved?.revision ?? 0 };
  const completed = !!saved?.completed_at;
  useEffect(() => {
    if (!draft) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [draft]);
  return <section className="section-panel mb-5 p-5" aria-labelledby="teacher-review-heading">
    <h2 id="teacher-review-heading" className="font-bold">{t("reviewGroups.teacherReview")}</h2>
    {completed ? <p role="status" className="mt-2 text-sm">{t("reviewGroups.completedAt", { date: formatDateTime(saved!.completed_at!) })}</p>
      : <p className="mt-2 text-sm text-[var(--color-muted)]">{t("reviewGroups.reviewHint")} {t("reviewGroups.finalReviewHint")}</p>}
    <label className="mt-3 block text-sm font-semibold">{t("reviewGroups.teacherRemarks")}
      <textarea className="input mt-1 w-full" rows={3} maxLength={10000} value={value.remarks} disabled={completed || busy}
        onChange={event => { setDraft({ ...value, remarks: event.target.value }); save.reset(); }} />
    </label>
    {save.isError && <ErrorState compact error={save.error} />}
    {reload.isError && <ErrorState compact error={reload.error} />}
    {save.isError && <button className="btn btn-secondary mt-2" disabled={reload.isPending || save.isPending}
      onClick={() => reload.mutate()}>{t("reviewGroups.reloadRemarks")}</button>}
    {save.isSuccess && !draft && !completed && <p role="status" className="text-sm">{t("reviewGroups.remarksSaved")}</p>}
    {draft && <p role="status" className="text-sm text-amber-900">{t("reviewGroups.unsavedRemarks")}</p>}
    <div className="mt-3 flex flex-wrap items-center gap-3">
      {!completed && <>
        <button className="btn btn-secondary" disabled={busy || !draft} onClick={() => save.mutate(value, { onSuccess: () => setDraft(null) })}>{t("reviewGroups.saveRemarks")}</button>
        <button className="btn btn-primary" disabled={busy || !ready || viewedJob?.status !== "COMPLETED" || !viewedJob.result_summary}
          onClick={() => { if (viewedJob) save.mutate({ ...value, job_id: viewedJob.id }, { onSuccess: () => setDraft(null) }); }}>{t("reviewGroups.completeReview")}</button>
        {ready && viewedJob && <span className="text-sm">{t("reviewGroups.completingRun", { number: viewedJob.run_number ?? 1 })}</span>}
        {!ready && <span className="text-sm text-[var(--color-muted)]">{t("reviewGroups.resultRequired")}</span>}
      </>}
      {completed && <>
        <p className="text-sm text-[var(--color-muted)]">{t("reviewGroups.pinnedResult")}</p>
        <button className="btn btn-secondary" onClick={() => onShowReviewedRun(saved!.completed_job_id!)}>{t("reviewGroups.showReviewedRun")}</button>
      </>}
    </div>
  </section>;
}
