import { useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { ExportButtons } from "../../components/ExportButtons";
import { StatusBadge } from "../../components/StatusBadge";
import { DocumentPreview } from "../documents/DocumentPreview";
import { BlockView } from "../documents/BlockView";
import { useReportDocument } from "../documents/api";
import { useGroupDetail } from "../groups/api";
import { ReportCollaborationPanel } from "./ReportCollaborationPanel";
import type { Block, DocumentModel } from "../../types/document";
import type { ReportDetail, ReportHistoryEntry, TeacherReviewQueueItem } from "../../types/api";
import { ArrowLeftIcon, ArrowRightIcon, ChatBubbleLeftEllipsisIcon, EyeIcon, PaperAirplaneIcon, CheckCircleIcon } from "@heroicons/react/24/outline";
import { ErrorState, LoadingState } from "../../components/ui/StateViews";
import { PaginationControls } from "../../components/ui/PaginationControls";
import { DEFAULT_PAGE_SIZE, fetchPage } from "../../lib/pagination";
import { useTranslation } from "react-i18next";
import { useLocaleFormatters } from "../../i18n/formatters";
import { getApiErrorPresentation } from "../../lib/apiError";
import { showToast } from "../../lib/toast";
import { useProductFeatures } from "../auth/useProductFeatures";

const EVENT_TRANSLATION_KEYS = {
  REPORT_SUBMITTED: "events.REPORT_SUBMITTED",
  REPORT_RESUBMITTED: "events.REPORT_RESUBMITTED",
  REVIEW_STARTED: "events.REVIEW_STARTED",
  REPORT_REVISION_REQUESTED: "events.REPORT_REVISION_REQUESTED",
  REPORT_APPROVED: "events.REPORT_APPROVED",
  REPORT_LOCKED: "events.REPORT_LOCKED",
  COMMENT_CREATED: "events.COMMENT_CREATED",
  COMMENT_REPLIED: "events.COMMENT_REPLIED",
  COMMENT_RESOLVED: "events.COMMENT_RESOLVED",
} as const;

type ReviewAction = "start" | "revision" | "approve";

function textForInlineComment(block: Block): string | null {
  if (block.type === "paragraph" || block.type === "heading") {
    const text = block.runs.filter((run) => run.kind === "text").map((run) => run.text).join("").trim();
    return text || null;
  }
  return null;
}

function ReviewDocument({ document, reportId, canComment }: { document: DocumentModel; reportId: string; canComment: boolean }) {
  const { t } = useTranslation(["reports", "common"]);
  const queryClient = useQueryClient();
  const [target, setTarget] = useState<{ id: string; text: string } | null>(null);
  const [body, setBody] = useState("");
  const createInline = useMutation({
    mutationFn: async () => api.post(`/reports/${reportId}/comments`, {
      node_id: target!.id, start_offset: 0, end_offset: target!.text.length, text_snapshot: target!.text, body,
    }),
    onSuccess: () => {
      setTarget(null);
      setBody("");
      void queryClient.invalidateQueries({ queryKey: ["reports", reportId, "comments"] });
    },
  });
  return (
    <div className="space-y-5">
      {document.sections.map((section) => (
        <section key={section.id} className="rounded-lg border border-[var(--color-border)] bg-white p-5">
          <h3 className="font-display text-lg font-bold text-[var(--color-ink)]">{section.title}</h3>
          <div className="mt-3 space-y-2">
            {section.blocks.map((block) => {
              const text = textForInlineComment(block);
              return <div key={block.id} className="group relative rounded-xl px-2 py-1.5 hover:bg-[var(--color-brand-50)]/50"><BlockView block={block} meta={document.meta} />{canComment && text && <button onClick={() => { setTarget({ id: block.id, text }); setBody(""); }} className="mt-1 inline-flex items-center gap-1 opacity-0 text-xs font-semibold text-[var(--color-brand-600)] transition-opacity group-hover:opacity-100 focus:opacity-100"><ChatBubbleLeftEllipsisIcon className="size-3.5" />{t("inlineComment")}</button>}</div>;
            })}
          </div>
        </section>
      ))}
      {target && <div className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--color-ink)]/35 p-4 backdrop-blur-[1px]" onClick={() => setTarget(null)}><form onClick={(e) => e.stopPropagation()} onSubmit={(e) => { e.preventDefault(); if (body.trim()) createInline.mutate(); }} className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-[var(--shadow-float)]"><h3 className="font-display text-lg font-bold text-[var(--color-ink)]">{t("inlineComment")}</h3><blockquote className="mt-3 border-l-2 border-[var(--color-brand-500)] pl-3 text-sm italic text-[var(--color-muted)]">«{target.text}»</blockquote><textarea autoFocus value={body} onChange={(e) => setBody(e.target.value)} className="input mt-4 min-h-24 resize-y" placeholder={t("inlineCommentPlaceholder")} /><div className="mt-4 flex justify-end gap-2"><button type="button" onClick={() => setTarget(null)} className="btn btn-ghost">{t("common:cancel")}</button><button disabled={!body.trim() || createInline.isPending} className="btn btn-primary">{t("common:add")}</button></div></form></div>}
    </div>
  );
}
export function TeacherReportPage() {
  const { t } = useTranslation("reports");
  const { formatCount, formatDate, formatDateTime } = useLocaleFormatters();
  const { legacy_document_editor_enabled: legacyDocumentEditorEnabled } = useProductFeatures();
  const { groupId, reportId } = useParams<{ groupId: string; reportId: string }>();
  const [searchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const [showPreview, setShowPreview] = useState(false);
  const [revisionNote, setRevisionNote] = useState("");
  const [approveConfirmationOpen, setApproveConfirmationOpen] = useState(false);
  const [reviewError, setReviewError] = useState<{ action: ReviewAction; error: unknown } | null>(null);
  const [historyOffset, setHistoryOffset] = useState(0);
  const groupQuery = useGroupDetail(groupId);
  const reportQuery = useQuery({ queryKey: ["reports", reportId], queryFn: async () => (await api.get<ReportDetail>(`/reports/${reportId}`)).data, enabled: !!reportId });
  const documentQuery = useReportDocument(reportId);
  const historyQuery = useQuery({ queryKey: ["reports", reportId, "history", { historyOffset }], queryFn: () => fetchPage<ReportHistoryEntry>(`/reports/${reportId}/history`, { offset: historyOffset, limit: DEFAULT_PAGE_SIZE }), enabled: !!reportId });
  const queueQuery = useMemo(() => {
    const params = new URLSearchParams();
    for (const key of ["status", "internship_id", "deadline", "student"]) {
      const value = searchParams.get(key);
      if (value) params.set(key, value);
    }
    return params.toString();
  }, [searchParams]);
  const queueReturnQuery = useMemo(() => {
    const params = new URLSearchParams(searchParams);
    params.set("tab", "reports");
    return params.toString();
  }, [searchParams]);
  const nextQueueQuery = useQuery({
    queryKey: ["groups", groupId, "review-queue", "next", reportId, queueQuery],
    queryFn: async () => (await api.get<TeacherReviewQueueItem | null>(`/groups/${groupId}/reports/${reportId}/next-in-queue${queueQuery ? `?${queueQuery}` : ""}`)).data,
    enabled: !!groupId && !!reportId,
  });
  const group = groupQuery.data?.data;
  const report = reportQuery.data;
  const documentData = documentQuery.data;
  const history = historyQuery.data?.items ?? [];
  const eventLabel = (event: string) => {
    const key = EVENT_TRANSLATION_KEYS[event as keyof typeof EVENT_TRANSLATION_KEYS];
    return key ? t(key) : t("unknownEvent");
  };
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["reports", reportId] });
    void queryClient.invalidateQueries({ queryKey: ["groups", groupId, "reports"] });
    void queryClient.invalidateQueries({ queryKey: ["reports", reportId, "history"] });
  };
  const startReview = useMutation({
    mutationFn: async () => api.post(`/reports/${reportId}/review/start`),
    onMutate: () => setReviewError(null),
    onSuccess: () => { refresh(); showToast(t("reviewStartedSuccess")); },
    onError: (error) => setReviewError({ action: "start", error }),
  });
  const approve = useMutation({
    mutationFn: async () => api.post(`/reports/${reportId}/review/approve`),
    onMutate: () => setReviewError(null),
    onSuccess: () => { setApproveConfirmationOpen(false); refresh(); showToast(t("reportApprovedSuccess")); },
    onError: (error) => setReviewError({ action: "approve", error }),
  });
  const requestRevision = useMutation({
    mutationFn: async () => api.post(`/reports/${reportId}/review/request-revision`, { general_comment: revisionNote.trim() }),
    onMutate: () => setReviewError(null),
    onSuccess: () => { setRevisionNote(""); refresh(); showToast(t("revisionRequestedSuccess")); },
    onError: (error) => setReviewError({ action: "revision", error }),
  });
  const student = useMemo(() => group?.students.find((item) => item.student_id === report?.student_id), [group, report]);
  const primaryError = reportQuery.isError ? reportQuery.error : documentQuery.isError ? documentQuery.error : null;
  const retryPrimary = () => {
    void reportQuery.refetch();
    void documentQuery.refetch();
  };

  if (reportQuery.isLoading || documentQuery.isLoading) return <LoadingState label={t("loadingReport")} />;
  if (primaryError) return <ErrorState error={primaryError} onRetry={retryPrimary} />;
  if (!report || !documentData) return <ErrorState message={t("reportUnavailable")} onRetry={retryPrimary} />;

  return (
    <div>
      <Link to={`/groups/${groupId}?${queueReturnQuery}`} className="inline-flex items-center gap-1.5 text-sm font-semibold text-[var(--color-muted)] hover:text-[var(--color-brand-600)]"><ArrowLeftIcon className="size-4" />{t("backToGroup", { name: group?.name ?? "" })}</Link>
      <header className="mt-4 border-b border-[var(--color-border)] bg-white p-5 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div><p className="text-xs font-medium uppercase tracking-wide text-[var(--color-muted)]">{t("studentReport")}</p><h1 className="mt-1 font-display text-2xl font-bold text-[var(--color-ink)]">{student?.full_name ?? t("student")}</h1><p className="mt-1 text-sm text-[var(--color-muted)]">{formatCount(report.versions.length, (values) => t("deadlineAndVersions", { date: formatDate(report.deadline), ...values }))}</p></div>
          <div className="flex flex-wrap items-center gap-2">{nextQueueQuery.data && <Link to={`/groups/${groupId}/reports/${nextQueueQuery.data.id}${queueQuery ? `?tab=reports&${queueQuery}` : "?tab=reports"}`} className="btn btn-secondary"><span>{t("nextReportInQueue")}</span><ArrowRightIcon className="size-4" /></Link>}<StatusBadge status={report.status} /><ExportButtons reportId={report.id} /></div>
        </div>
        <div className="mt-5 flex flex-wrap gap-2 border-t border-[var(--color-border)] pt-4">
          {report.status === "SUBMITTED" && <button onClick={() => startReview.mutate()} disabled={startReview.isPending} className="btn btn-primary"><EyeIcon className="size-4" />{t("startReview")}</button>}
          {report.status === "UNDER_REVIEW" && <>{legacyDocumentEditorEnabled && <><label className="min-w-60 flex-1"><span className="sr-only">{t("revisionNoteLabel")}</span><textarea value={revisionNote} onChange={(event) => setRevisionNote(event.target.value)} className="input min-h-20 w-full resize-y" placeholder={t("revisionNotePlaceholder")} aria-describedby="revision-note-help" required /></label><div className="flex flex-col gap-1"><button onClick={() => requestRevision.mutate()} disabled={!revisionNote.trim() || requestRevision.isPending} className="btn bg-[var(--color-amber-500)] text-white hover:brightness-95"><PaperAirplaneIcon className="size-4" />{t("requestRevision")}</button><p id="revision-note-help" className="text-xs text-[var(--color-muted)]">{t("revisionNoteRequired")}</p></div></>}<button onClick={() => { setReviewError(null); setApproveConfirmationOpen(true); }} disabled={approve.isPending} className="btn bg-[var(--color-success-500)] text-white hover:brightness-95"><CheckCircleIcon className="size-4" />{t("approveAndClose")}</button></>}
          {report.status === "REVISION_REQUIRED" && <p className="text-sm text-[var(--color-amber-500)]">{t("awaitingRevision")}</p>}
          {report.status === "LOCKED" && <p className="text-sm text-[var(--color-success-500)]">{t("reportLocked")}</p>}
        </div>
        {reviewError && reviewError.action !== "approve" && <ReviewActionError error={reviewError.error} />}
      </header>

      {groupQuery.isError && <div className="mt-4"><ErrorState compact error={groupQuery.error} message={t("groupLoadWarning")} onRetry={() => void groupQuery.refetch()} /></div>}

      <div className="mt-6 grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div><div className="mb-3 flex items-center justify-between"><h2 className="font-display text-lg font-bold text-[var(--color-ink)]">{t("document")}</h2><button onClick={() => setShowPreview((current) => !current)} className="btn btn-ghost px-2 py-1.5 text-[var(--color-brand-600)]"><EyeIcon className="size-4" />{showPreview ? t("reviewMode") : t("previewA4")}</button></div>{showPreview ? <div className="overflow-x-auto"><DocumentPreview document={documentData.document} numbering={documentData.numbering} /></div> : <ReviewDocument document={documentData.document} reportId={report.id} canComment={report.status === "UNDER_REVIEW" || report.status === "REVISION_REQUIRED"} />}</div>
        <aside className="space-y-5"><ReportCollaborationPanel reportId={report.id} canManage={report.status === "UNDER_REVIEW" || report.status === "REVISION_REQUIRED"} /><section className="card p-5"><h2 className="font-display text-lg font-bold text-[var(--color-ink)]">{t("history")}</h2><div className="mt-4 space-y-3">{historyQuery.isLoading && <LoadingState label={t("loadingHistory")} />}{historyQuery.isError && <ErrorState compact error={historyQuery.error} onRetry={() => void historyQuery.refetch()} />}{!historyQuery.isLoading && !historyQuery.isError && history.length === 0 && <p className="text-sm text-[var(--color-muted)]">{t("noHistory")}</p>}{!historyQuery.isError && history.map((event, index) => <div key={`${event.created_at}-${index}`} className="border-l-2 border-[var(--color-brand-100)] pl-3"><p className="text-sm font-medium text-[var(--color-ink-soft)]">{eventLabel(event.event)}</p><p className="mt-0.5 text-xs text-[var(--color-muted)]">{event.actor_name ?? t("systemActor")} · {formatDateTime(event.created_at)}</p></div>)}</div>{!historyQuery.isError && historyQuery.data && <PaginationControls pagination={historyQuery.data} onPageChange={setHistoryOffset} isFetching={historyQuery.isFetching} label={t("history")} />}</section></aside>
      </div>
      {approveConfirmationOpen && <ApproveConfirmationDialog studentName={student?.full_name ?? t("student")} internshipTitle={report.internship_title} deadline={formatDate(report.deadline)} isPending={approve.isPending} error={reviewError?.action === "approve" ? reviewError.error : null} onCancel={() => { setApproveConfirmationOpen(false); setReviewError(null); }} onConfirm={() => approve.mutate()} />}
    </div>
  );
}

function ReviewActionError({ error }: { error: unknown }) {
  const { t } = useTranslation("reports");
  const presentation = getApiErrorPresentation(error, "reports");
  return <div className="mt-3 rounded-xl border border-[var(--color-danger-500)]/30 bg-[var(--color-danger-50)] px-4 py-3" role="alert"><p className="text-sm font-semibold text-[var(--color-ink)]">{t("reviewActionFailed")}</p><p className="mt-1 text-sm text-[var(--color-danger-500)]">{presentation.description}</p></div>;
}

function ApproveConfirmationDialog({ studentName, internshipTitle, deadline, isPending, error, onCancel, onConfirm }: { studentName: string; internshipTitle: string; deadline: string; isPending: boolean; error: unknown | null; onCancel: () => void; onConfirm: () => void }) {
  const { t } = useTranslation(["reports", "common"]);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--color-ink)]/35 p-4 backdrop-blur-[1px]" role="presentation">
      <section className="card w-full max-w-md p-6" role="dialog" aria-modal="true" aria-labelledby="approve-confirmation-title">
        <h2 id="approve-confirmation-title" className="font-display text-xl font-bold text-[var(--color-ink)]">{t("approveConfirmationTitle")}</h2>
        <p className="mt-3 text-sm leading-6 text-[var(--color-ink-soft)]">{t("approveConfirmationDescription")}</p>
        <dl className="mt-4 space-y-2 rounded-xl bg-[var(--color-surface)] p-4 text-sm"><div className="flex justify-between gap-4"><dt className="text-[var(--color-muted)]">{t("approveConfirmationStudent")}</dt><dd className="text-right font-medium text-[var(--color-ink)]">{studentName}</dd></div><div className="flex justify-between gap-4"><dt className="text-[var(--color-muted)]">{t("approveConfirmationInternship")}</dt><dd className="text-right font-medium text-[var(--color-ink)]">{internshipTitle}</dd></div><div className="flex justify-between gap-4"><dt className="text-[var(--color-muted)]">{t("approveConfirmationDeadline")}</dt><dd className="text-right font-medium text-[var(--color-ink)]">{deadline}</dd></div></dl>
        <p className="mt-4 rounded-xl bg-[var(--color-amber-50)] px-3 py-2.5 text-sm font-medium text-[var(--color-amber-500)]">{t("approveConfirmationWarning")}</p>
        {error !== null && <ReviewActionError error={error} />}
        <div className="mt-6 flex justify-end gap-2"><button type="button" onClick={onCancel} disabled={isPending} className="btn btn-secondary">{t("common:cancel")}</button><button type="button" onClick={onConfirm} disabled={isPending} className="btn bg-[var(--color-success-500)] text-white hover:brightness-95">{isPending ? t("approving") : t("approveAndClose")}</button></div>
      </section>
    </div>
  );
}
