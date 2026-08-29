import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../../lib/api";
import { ArrowRightIcon, KeyIcon, LockClosedIcon } from "@heroicons/react/24/outline";
import { getApiErrorPresentation } from "../../lib/apiError";

export function CompleteAccessPage() {
  const [params] = useSearchParams();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [state, setState] = useState<"idle" | "saving" | "done" | "error">("idle");
  const [error, setError] = useState<unknown>(null);
  const token = params.get("token");
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!token || password !== confirm || password.length < 8) return;
    setState("saving");
    try { await api.post("/auth/complete-access", { token, password }); setState("done"); } catch (requestError) { setError(requestError); setState("error"); }
  };
  const errorMessage = error !== null ? getApiErrorPresentation(error).description : "Ссылка недействительна или срок её действия истёк.";
  return <div className="flex min-h-screen items-center justify-center bg-[var(--color-surface)] p-4"><div className="card w-full max-w-md p-7"><div className="flex size-11 items-center justify-center rounded-xl bg-[var(--color-brand-50)] text-[var(--color-brand-600)]"><KeyIcon className="size-6" /></div><p className="mt-4 font-display text-xl font-extrabold text-[var(--color-ink)]">PracticeFlow</p><h1 className="mt-5 font-display text-2xl font-bold text-[var(--color-ink)]">Установите пароль</h1>{state === "done" ? <div className="mt-4"><p className="rounded-xl bg-[var(--color-success-50)] px-3 py-2.5 text-sm font-medium text-[var(--color-success-500)]">Пароль сохранён. Теперь можно войти в аккаунт.</p><Link to="/login" className="btn btn-primary mt-5">Перейти ко входу<ArrowRightIcon className="size-4" /></Link></div> : <form onSubmit={submit} className="mt-5 space-y-4"><p className="text-sm leading-6 text-[var(--color-muted)]">Эта ссылка одноразовая и действует семь дней.</p><label className="block"><span className="form-label flex items-center gap-1.5"><LockClosedIcon className="size-4" />Новый пароль</span><input type="password" value={password} onChange={(e) => setPassword(e.target.value)} className="input" minLength={8} required /></label><label className="block"><span className="form-label flex items-center gap-1.5"><LockClosedIcon className="size-4" />Повторите пароль</span><input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} className="input" minLength={8} required /></label>{(password && confirm && password !== confirm) && <p className="text-sm font-medium text-[var(--color-danger-500)]">Пароли не совпадают.</p>}{state === "error" && <p className="rounded-xl bg-[var(--color-danger-50)] px-3 py-2.5 text-sm font-medium text-[var(--color-danger-500)]" role="alert">{errorMessage}</p>}<button disabled={!token || password !== confirm || password.length < 8 || state === "saving"} className="btn btn-primary w-full">{state === "saving" ? "Сохранение…" : "Сохранить пароль"}</button></form>}</div></div>;
}
