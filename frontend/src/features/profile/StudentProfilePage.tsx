import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../lib/api";
import type { StudentProfile } from "../../types/api";
import { AcademicCapIcon, PencilSquareIcon, UserCircleIcon } from "@heroicons/react/24/outline";
import { ErrorState, LoadingState } from "../../components/ui/StateViews";

export function StudentProfilePage() {
  const queryClient = useQueryClient();
  const { data: profile, isLoading, isError, error, refetch } = useQuery({ queryKey: ["profile"], queryFn: async () => (await api.get<StudentProfile>("/profile")).data });
  const [fullName, setFullName] = useState("");
  const [editing, setEditing] = useState(false);
  useEffect(() => { if (profile) setFullName(profile.full_name); }, [profile]);
  const update = useMutation({
    mutationFn: async () => (await api.patch<StudentProfile>("/profile", { full_name: fullName.trim() })).data,
    onSuccess: (data) => { queryClient.setQueryData(["profile"], data); setEditing(false); },
  });

  if (isLoading) return <LoadingState label="Загрузка профиля…" />;
  if (isError) return <ErrorState error={error} onRetry={() => void refetch()} />;
  if (!profile) return <ErrorState message="Профиль не вернул данные. Повторите попытку." onRetry={() => void refetch()} />;
  return (
    <div className="max-w-3xl">
      <header className="mb-7"><p className="page-kicker">Личный кабинет</p><h1 className="page-title mt-1">Мой профиль</h1><p className="page-description">Контакты и академический контекст, используемые в документах.</p></header>
      <div className="grid gap-5 md:grid-cols-[1.2fr_0.8fr]">
        <section className="card p-6">
          <div className="flex items-center justify-between"><div className="flex items-center gap-3"><div className="flex size-10 items-center justify-center rounded-xl bg-[var(--color-brand-50)] text-[var(--color-brand-600)]"><UserCircleIcon className="size-5" /></div><h2 className="font-display text-lg font-bold text-[var(--color-ink)]">Данные студента</h2></div>{!editing && <button onClick={() => setEditing(true)} className="btn btn-ghost px-2 py-1.5 text-[var(--color-brand-600)]"><PencilSquareIcon className="size-4" />Изменить имя</button>}</div>
          {editing ? <form onSubmit={(e) => { e.preventDefault(); if (fullName.trim()) update.mutate(); }} className="mt-5"><label className="block"><span className="form-label">Полное имя</span><input autoFocus value={fullName} onChange={(e) => setFullName(e.target.value)} className="input" /></label><div className="mt-4 flex justify-end gap-2"><button type="button" onClick={() => { setFullName(profile.full_name); setEditing(false); }} className="btn btn-ghost">Отмена</button><button disabled={!fullName.trim() || update.isPending} className="btn btn-primary">Сохранить</button></div></form> : <dl className="mt-5 space-y-4"><Field label="Полное имя" value={profile.full_name} /><Field label="Email" value={profile.email} /><Field label="Специальность" value={profile.specialty_name ?? "Не указана"} /></dl>}
        </section>
        <section className="card p-6"><div className="flex items-center gap-2 text-[var(--color-muted)]"><AcademicCapIcon className="size-4" /><p className="text-sm font-semibold">Назначенные отчёты</p></div><p className="mt-2 font-display text-4xl font-extrabold text-[var(--color-ink)]">{profile.reports_count}</p><div className="mt-6 border-t border-[var(--color-border)] pt-4"><p className="text-sm font-bold text-[var(--color-ink)]">Мои группы</p><div className="mt-3 space-y-2">{profile.groups.length ? profile.groups.map((group) => <div key={group.id} className="rounded-xl bg-[var(--color-surface)] px-3 py-2.5"><p className="font-mono-code text-sm font-semibold text-[var(--color-ink)]">{group.name}</p>{group.academic_year && <p className="mt-0.5 text-xs text-[var(--color-muted)]">{group.academic_year}</p>}</div>) : <p className="text-sm text-[var(--color-muted)]">Группа пока не назначена.</p>}</div></div></section>
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return <div><dt className="text-xs font-medium uppercase tracking-wide text-[var(--color-muted)]">{label}</dt><dd className="mt-1 text-sm text-[var(--color-ink)]">{value}</dd></div>;
}
