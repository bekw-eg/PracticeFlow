import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../lib/api";
import type { ReportComment } from "../../types/api";
import { ChatBubbleLeftRightIcon, PaperAirplaneIcon } from "@heroicons/react/24/outline";
import { ErrorState, LoadingState } from "../../components/ui/StateViews";
import { PaginationControls } from "../../components/ui/PaginationControls";
import { DEFAULT_PAGE_SIZE, fetchPage } from "../../lib/pagination";
import { useTranslation } from "react-i18next";
import { useLocaleFormatters } from "../../i18n/formatters";

export function ReportCollaborationPanel({ reportId, canManage = false }: { reportId: string; canManage?: boolean }) {
  const { t } = useTranslation("reports");
  const { formatDateTime, formatNumber } = useLocaleFormatters();
  const queryClient = useQueryClient();
  const [generalComment, setGeneralComment] = useState("");
  const [replyFor, setReplyFor] = useState<string | null>(null);
  const [reply, setReply] = useState("");
  const [offset, setOffset] = useState(0);
  const { data: page, isLoading, isFetching, isError, error, refetch } = useQuery({
    queryKey: ["reports", reportId, "comments", { offset }],
    queryFn: () => fetchPage<ReportComment>(`/reports/${reportId}/comments`, { offset, limit: DEFAULT_PAGE_SIZE }),
  });
  const comments = page?.items ?? [];
  const refresh = () => void queryClient.invalidateQueries({ queryKey: ["reports", reportId, "comments"] });
  const createGeneral = useMutation({
    mutationFn: async (body: string) => api.post(`/reports/${reportId}/comments/general`, { body }),
    onSuccess: () => { setGeneralComment(""); refresh(); },
  });
  const replyMutation = useMutation({
    mutationFn: async ({ commentId, body }: { commentId: string; body: string }) => api.post(`/reports/${reportId}/comments/${commentId}/replies`, { body }),
    onSuccess: () => { setReply(""); setReplyFor(null); refresh(); },
  });
  const resolve = useMutation({
    mutationFn: async (commentId: string) => api.post(`/reports/${reportId}/comments/${commentId}/resolve`),
    onSuccess: refresh,
  });

  return (
    <section className="section-panel p-5">
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2"><ChatBubbleLeftRightIcon className="size-5 text-[var(--color-brand-600)]" /><h2 className="font-display text-lg font-bold text-[var(--color-ink)]">{t("discussion")}</h2></div>
          <p className="mt-1 text-xs text-[var(--color-muted)]">{t("discussionDescription")}</p>
        </div>
        <span className="rounded-[4px] border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-1 text-xs text-[var(--color-muted)]">{formatNumber(page?.total ?? comments.length)}</span>
      </div>

      {canManage && (
        <form onSubmit={(e) => { e.preventDefault(); if (generalComment.trim()) createGeneral.mutate(generalComment.trim()); }} className="mt-4">
          <textarea value={generalComment} onChange={(e) => setGeneralComment(e.target.value)} className="input min-h-20 resize-y" placeholder={t("generalCommentPlaceholder")} />
          <div className="mt-2 flex justify-end">
            <button disabled={!generalComment.trim() || createGeneral.isPending} className="btn btn-primary px-3 py-2 text-xs">{t("addComment")}</button>
          </div>
        </form>
      )}

      {isLoading && <div className="mt-4"><LoadingState label={t("loadingDiscussion")} /></div>}
      {isError && <div className="mt-4"><ErrorState compact error={error} onRetry={() => void refetch()} /></div>}
      {!isLoading && !isError && comments.length === 0 && <p className="mt-5 text-sm text-[var(--color-muted)]">{t("noComments")}</p>}

      <div className="mt-4 space-y-3">
        {!isError && comments.map((comment) => (
          <article key={comment.id} className="rounded-[6px] border border-[var(--color-border)] bg-[var(--color-surface)] p-3.5">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-[var(--color-ink)]">{comment.author.full_name}</p>
                <p className="mt-0.5 text-xs text-[var(--color-muted)]">{formatDateTime(comment.created_at)} · {comment.is_general ? t("commentGeneral") : t("commentFragment")}</p>
              </div>
              <div className="flex items-center gap-2">
                {!comment.is_general && comment.anchor_status && (
                  <span className={`rounded-[4px] px-2 py-0.5 text-[10px] font-medium ${comment.anchor_status === "valid" ? "bg-[var(--color-success-50)] text-[var(--color-success-500)]" : "bg-[var(--color-amber-50)] text-[var(--color-amber-500)]"}`}>
                    {comment.anchor_status === "valid" ? t("anchorValid") : t("anchorChanged")}
                  </span>
                )}
                <span className={`rounded-[4px] px-2 py-0.5 text-[10px] font-medium ${comment.status === "RESOLVED" ? "bg-[var(--color-success-50)] text-[var(--color-success-500)]" : "bg-white text-[var(--color-muted)]"}`}>{comment.status === "RESOLVED" ? t("commentResolved") : t("commentOpen")}</span>
              </div>
            </div>
            {!comment.is_general && comment.text_snapshot && <blockquote className="mt-2 border-l-2 border-[var(--color-brand-500)] pl-2 text-xs italic text-[var(--color-muted)]">«{comment.text_snapshot}»</blockquote>}
            <p className="mt-2 whitespace-pre-wrap text-sm text-[var(--color-ink-soft)]">{comment.body}</p>
            {comment.replies.map((item) => <div key={item.id} className="mt-2 border-l border-[var(--color-border)] pl-3"><p className="text-xs font-semibold text-[var(--color-ink)]">{item.author.full_name}</p><p className="mt-0.5 text-sm text-[var(--color-ink-soft)]">{item.body}</p></div>)}
            {comment.status === "OPEN" && (
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <button onClick={() => { setReplyFor(replyFor === comment.id ? null : comment.id); setReply(""); }} className="text-xs font-medium text-[var(--color-brand-600)]">{t("reply")}</button>
                {canManage && <button onClick={() => resolve.mutate(comment.id)} disabled={resolve.isPending} className="text-xs font-medium text-[var(--color-success-500)]">{t("markResolved")}</button>}
              </div>
            )}
            {replyFor === comment.id && <form onSubmit={(e) => { e.preventDefault(); if (reply.trim()) replyMutation.mutate({ commentId: comment.id, body: reply.trim() }); }} className="mt-3 flex gap-2"><input autoFocus value={reply} onChange={(e) => setReply(e.target.value)} className="input" placeholder={t("replyPlaceholder")}/><button className="btn btn-secondary px-3 text-xs text-[var(--color-brand-600)]"><PaperAirplaneIcon className="size-3.5" />{t("sendReply")}</button></form>}
          </article>
        ))}
      </div>
      {!isError && page && <PaginationControls pagination={page} onPageChange={setOffset} isFetching={isFetching} label={t("comments")} />}
    </section>
  );
}
