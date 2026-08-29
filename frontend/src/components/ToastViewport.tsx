import { useEffect, useState } from "react";
import type { ToastTone } from "../lib/toast";
import { CheckCircleIcon, InformationCircleIcon, XCircleIcon, XMarkIcon } from "@heroicons/react/24/solid";

type Toast = { id: number; message: string; tone: ToastTone };

export function ToastViewport() {
  const [items, setItems] = useState<Toast[]>([]);
  useEffect(() => {
    const handler = (event: Event) => {
      const { message, tone } = (event as CustomEvent<Omit<Toast, "id">>).detail;
      const id = Date.now() + Math.random();
      setItems((current) => [...current, { id, message, tone }]);
      window.setTimeout(() => setItems((current) => current.filter((item) => item.id !== id)), 4500);
    };
    window.addEventListener("pf:toast", handler);
    return () => window.removeEventListener("pf:toast", handler);
  }, []);
  return <div className="fixed bottom-4 right-4 z-[100] flex w-[min(380px,calc(100vw-2rem))] flex-col gap-2">{items.map((item) => { const ToneIcon = item.tone === "error" ? XCircleIcon : item.tone === "info" ? InformationCircleIcon : CheckCircleIcon; return <div key={item.id} className={`rounded-2xl px-4 py-3.5 text-sm font-medium shadow-[var(--shadow-float)] ${item.tone === "error" ? "bg-[var(--color-danger-500)] text-white" : item.tone === "info" ? "bg-[var(--color-ink)] text-white" : "bg-[var(--color-success-500)] text-white"}`}><div className="flex items-start gap-3"><ToneIcon className="mt-0.5 size-5 shrink-0" /><span className="flex-1 leading-5">{item.message}</span><button onClick={() => setItems((current) => current.filter((entry) => entry.id !== item.id))} className="-mr-1 -mt-1 rounded-lg p-1 hover:bg-white/15" aria-label="Закрыть уведомление"><XMarkIcon className="size-4" /></button></div></div>; })}</div>;
}
