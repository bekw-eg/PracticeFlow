import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import type { NotificationOut } from "../types/api";
import { BellIcon, CheckIcon, InboxIcon } from "@heroicons/react/24/outline";
import { ErrorState, LoadingState } from "./ui/StateViews";
import { PaginationControls } from "./ui/PaginationControls";
import { DEFAULT_PAGE_SIZE, fetchPage } from "../lib/pagination";

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const [offset, setOffset] = useState(0);
  const queryClient = useQueryClient();
  const { data: page, isLoading, isFetching, isError, error, refetch } = useQuery({ queryKey: ["notifications", { offset }], queryFn: () => fetchPage<NotificationOut>("/notifications", { offset, limit: DEFAULT_PAGE_SIZE }), refetchInterval: 30_000 });
  const readAll = useMutation({ mutationFn: async () => api.post("/notifications/read-all"), onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["notifications"] }) });
  const items = page?.items ?? [];
  const unread = items.filter((item) => !item.read_at).length;
  return <div className="relative"><button onClick={() => setOpen((value) => !value)} className="icon-button relative" aria-label="Уведомления" aria-expanded={open}><BellIcon className="size-5" aria-hidden="true" />{unread > 0 && <span className="absolute right-1 top-1 min-w-4 rounded-full bg-[var(--color-danger-500)] px-1 text-center text-[10px] font-bold leading-4 text-white">{unread > 9 ? "9+" : unread}</span>}</button>{open && <div className="absolute right-0 z-50 mt-2 w-[min(22rem,calc(100vw-2rem))] overflow-hidden rounded-2xl border border-[var(--color-border)] bg-white shadow-[var(--shadow-float)]"><div className="flex items-center justify-between border-b border-[var(--color-border)] px-4 py-3.5"><p className="font-display font-bold text-[var(--color-ink)]">Уведомления</p>{unread > 0 && <button onClick={() => readAll.mutate()} className="inline-flex items-center gap-1 text-xs font-semibold text-[var(--color-brand-600)]"><CheckIcon className="size-3.5" />Прочитать всё</button>}</div><div className="max-h-96 overflow-y-auto">{isLoading && <div className="p-4"><LoadingState label="Загрузка уведомлений…" /></div>}{isError && <div className="p-4"><ErrorState compact error={error} onRetry={() => void refetch()} /></div>}{!isLoading && !isError && items.length === 0 && <div className="p-7 text-center"><InboxIcon className="mx-auto size-6 text-[var(--color-muted)]" /><p className="mt-2 text-sm text-[var(--color-muted)]">Новых событий нет.</p></div>}{!isError && items.map((item) => <Link key={item.id} onClick={() => setOpen(false)} to={item.link ?? "#"} className={`block border-b border-[var(--color-border)] px-4 py-3.5 transition-colors last:border-0 hover:bg-[var(--color-surface)] ${item.read_at ? "bg-white" : "bg-[var(--color-brand-50)]"}`}><p className="text-sm font-semibold text-[var(--color-ink)]">{item.title}</p>{item.body && <p className="mt-1 text-xs leading-5 text-[var(--color-muted)]">{item.body}</p>}</Link>)}{!isError && page && <div className="px-4 pb-3"><PaginationControls pagination={page} onPageChange={setOffset} isFetching={isFetching} label="Уведомления" /></div>}</div></div>}</div>;
}
