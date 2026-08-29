import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
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
import type { ReportDetail, ReportHistoryEntry } from "../../types/api";
import { ArrowLeftIcon, ChatBubbleLeftEllipsisIcon, EyeIcon, PaperAirplaneIcon, CheckCircleIcon } from "@heroicons/react/24/outline";
import { ErrorState, LoadingState } from "../../components/ui/StateViews";
import { PaginationControls } from "../../components/ui/PaginationControls";
import { DEFAULT_PAGE_SIZE, fetchPage } from "../../lib/pagination";

function formatDate(value: string) {
  return new Intl.DateTimeFormat("ru-RU", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function textForInlineComment(block: Block): string | null {
  if (block.type === "paragraph" || block.type === "heading") {
    const text = block.runs.filter((run) => run.kind === "text").map((run) => run.text).join("").trim();
    return text || null;
  }
  return null;
}

function ReviewDocument({ document, reportId, canComment }: { document: DocumentModel; reportId: string; canComment: boolean }) {
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
        <section key={section.id} className="rounded-xl border border-[var(--color-border)] bg-white p-5">
          <h3 className="font-display text-lg font-bold text-[var(--color-ink)]">{section.title}</h3>
          <div className="mt-3 space-y-2">
            {section.blocks.map((block) => {
              const text = textForInlineComment(block);
              return <div key={block.id} className="group relative rounded-xl px-2 py-1.5 hover:bg-[var(--color-brand-50)]/50"><BlockView block={block} meta={document.meta} />{canComment && text && <button onClick={() => { setTarget({ id: block.id, text }); setBody(""); }} className="mt-1 inline-flex items-center gap-1 opacity-0 text-xs font-semibold text-[var(--color-brand-600)] transition-opacity group-hover:opacity-100 focus:opacity-100"><ChatBubbleLeftEllipsisIcon className="size-3.5" />Комментарий к фрагменту</button>}</div>;
            })}
          </div>
        </section>
      ))}
      {target && <div className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--color-ink)]/35 p-4 backdrop-blur-[1px]" onClick={() => setTarget(null)}><form onClick={(e) => e.stopPropagation()} onSubmit={(e) => { e.preventDefault(); if (body.trim()) createInline.mutate(); }} className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-[var(--shadow-float)]"><h3 className="font-display text-lg font-bold text-[var(--color-ink)]">Комментарий к фрагменту</h3><blockquote className="mt-3 border-l-2 border-[var(--color-brand-500)] pl-3 text-sm italic text-[var(--color-muted)]">«{target.text}»</blockquote><textarea autoFocus value={body} onChange={(e) => setBody(e.target.value)} className="input mt-4 min-h-24 resize-y" placeholder="Что нужно исправить?" /><div className="mt-4 flex justify-end gap-2"><button type="button" onClick={() => setTarget(null)} className="btn btn-ghost">Отмена</button><button disabled={!body.trim() || createInline.isPending} className="btn btn-primary">Добавить</button></div></form></div>}
    </div>
  );
}

export function TeacherReportPage() {
  const { groupId, reportId } = useParams<{ groupId: string; reportId: string }>();
  const queryClient = useQueryClient();
  const [showPreview, setShowPreview] = useState(false);
  const [revisionNote, setRevisionNote] = useState("");
  const [historyOffset, setHistoryOffset] = useState(0);
  const groupQuery = useGroupDetail(groupId);
  const reportQuery = useQuery({ queryKey: ["reports", reportId], queryFn: async () => (await api.get<ReportDetail>(`/reports/${reportId}`)).data, enabled: !!reportId });
  const documentQuery = useReportDocument(reportId);
  const historyQuery = useQuery({ queryKey: ["reports", reportId, "history", { historyOffset }], queryFn: () => fetchPage<ReportHistoryEntry>(`/reports/${reportId}/history`, { offset: historyOffset, limit: DEFAULT_PAGE_SIZE }), enabled: !!reportId });
  const group = groupQuery.data?.data;
  const report = reportQuery.data;
  const documentData = documentQuery.data;
  const history = historyQuery.data?.items ?? [];
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["reports", reportId] });
    void queryClient.invalidateQueries({ queryKey: ["groups", groupId, "reports"] });
    void queryClient.invalidateQueries({ queryKey: ["reports", reportId, "history"] });
  };
  const startReview = useMutation({ mutationFn: async () => api.post(`/reports/${reportId}/review/start`), onSuccess: refresh });
  const approve = useMutation({ mutationFn: async () => api.post(`/reports/${reportId}/review/approve`), onSuccess: refresh });
  const requestRevision = useMutation({ mutationFn: async () => api.post(`/reports/${reportId}/review/request-revision`, { general_comment: revisionNote.trim() || null }), onSuccess: () => { setRevisionNote(""); refresh(); } });
  const student = useMemo(() => group?.students.find((item) => item.student_id === report?.student_id), [group, report]);
  const primaryError = reportQuery.isError ? reportQuery.error : documentQuery.isError ? documentQuery.error : null;
  const retryPrimary = () => {
    void reportQuery.refetch();
    void documentQuery.refetch();
  };

  if (reportQuery.isLoading || documentQuery.isLoading) return <LoadingState label="Загрузка отчёта…" />;
  if (primaryError) return <ErrorState error={primaryError} onRetry={retryPrimary} />;
  if (!report || !documentData) return <ErrorState message="Отчёт не вернул необходимые данные. Повторите попытку." onRetry={retryPrimary} />;

  return (
    <div>
      <Link to={`/groups/${groupId}`} className="inline-flex items-center gap-1.5 text-sm font-semibold text-[var(--color-muted)] hover:text-[var(--color-brand-600)]"><ArrowLeftIcon className="size-4" />К группе {group?.name ?? ""}</Link>
      <header className="card mt-4 p-5 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div><p className="text-xs font-medium uppercase tracking-wide text-[var(--color-muted)]">Отчёт студента</p><h1 className="mt-1 font-display text-2xl font-bold text-[var(--color-ink)]">{student?.full_name ?? "Студент"}</h1><p className="mt-1 text-sm text-[var(--color-muted)]">Дедлайн: {new Intl.DateTimeFormat("ru-RU", { dateStyle: "medium" }).format(new Date(report.deadline))} · Версий: {report.versions.length}</p></div>
          <div className="flex flex-wrap items-center gap-2"><StatusBadge status={report.status} /><ExportButtons reportId={report.id} /></div>
        </div>
        <div className="mt-5 flex flex-wrap gap-2 border-t border-[var(--color-border)] pt-4">
          {report.status === "SUBMITTED" && <button onClick={() => startReview.mutate()} disabled={startReview.isPending} className="btn btn-primary"><EyeIcon className="size-4" />Начать проверку</button>}
          {report.status === "UNDER_REVIEW" && <><input value={revisionNote} onChange={(e) => setRevisionNote(e.target.value)} className="input max-w-sm" placeholder="Итоговый комментарий при возврате (необязательно)" /><button onClick={() => requestRevision.mutate()} disabled={requestRevision.isPending} className="btn bg-[var(--color-amber-500)] text-white hover:brightness-95"><PaperAirplaneIcon className="size-4" />Вернуть на доработку</button><button onClick={() => approve.mutate()} disabled={approve.isPending} className="btn bg-[var(--color-success-500)] text-white hover:brightness-95"><CheckCircleIcon className="size-4" />Утвердить и закрыть</button></>}
          {report.status === "REVISION_REQUIRED" && <p className="text-sm text-[var(--color-amber-500)]">Ожидается доработанная версия от студента.</p>}
          {report.status === "LOCKED" && <p className="text-sm text-[var(--color-success-500)]">Отчёт утверждён и заблокирован для изменений.</p>}
        </div>
      </header>

      {groupQuery.isError && <div className="mt-4"><ErrorState compact error={groupQuery.error} message="Не удалось получить данные группы. Отчёт остаётся доступен, но имя студента может не отображаться." onRetry={() => void groupQuery.refetch()} /></div>}

      <div className="mt-6 grid gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div><div className="mb-3 flex items-center justify-between"><h2 className="font-display text-lg font-bold text-[var(--color-ink)]">Документ</h2><button onClick={() => setShowPreview((current) => !current)} className="btn btn-ghost px-2 py-1.5 text-[var(--color-brand-600)]"><EyeIcon className="size-4" />{showPreview ? "Режим проверки" : "Предпросмотр A4"}</button></div>{showPreview ? <div className="overflow-x-auto"><DocumentPreview document={documentData.document} numbering={documentData.numbering} /></div> : <ReviewDocument document={documentData.document} reportId={report.id} canComment={report.status === "UNDER_REVIEW" || report.status === "REVISION_REQUIRED"} />}</div>
        <aside className="space-y-5"><ReportCollaborationPanel reportId={report.id} canManage={report.status === "UNDER_REVIEW" || report.status === "REVISION_REQUIRED"} /><section className="card p-5"><h2 className="font-display text-lg font-bold text-[var(--color-ink)]">История</h2><div className="mt-4 space-y-3">{historyQuery.isLoading && <LoadingState label="Загрузка истории…" />}{historyQuery.isError && <ErrorState compact error={historyQuery.error} onRetry={() => void historyQuery.refetch()} />}{!historyQuery.isLoading && !historyQuery.isError && history.length === 0 && <p className="text-sm text-[var(--color-muted)]">Событий пока нет.</p>}{!historyQuery.isError && history.map((event, index) => <div key={`${event.created_at}-${index}`} className="border-l-2 border-[var(--color-brand-100)] pl-3"><p className="text-sm font-medium text-[var(--color-ink-soft)]">{eventLabel(event.event)}</p><p className="mt-0.5 text-xs text-[var(--color-muted)]">{event.actor_name ?? "Система"} · {formatDate(event.created_at)}</p></div>)}</div>{!historyQuery.isError && historyQuery.data && <PaginationControls pagination={historyQuery.data} onPageChange={setHistoryOffset} isFetching={historyQuery.isFetching} label="История" />}</section></aside>
      </div>
    </div>
  );
}

function eventLabel(event: string) {
  const labels: Record<string, string> = { REPORT_SUBMITTED: "Отчёт отправлен", REPORT_RESUBMITTED: "Отчёт отправлен повторно", REVIEW_STARTED: "Проверка начата", REPORT_REVISION_REQUESTED: "Запрошена доработка", REPORT_APPROVED: "Отчёт утверждён", REPORT_LOCKED: "Отчёт заблокирован", COMMENT_CREATED: "Добавлен комментарий", COMMENT_REPLIED: "Добавлен ответ", COMMENT_RESOLVED: "Комментарий решён" };
  return labels[event] ?? event;
}
