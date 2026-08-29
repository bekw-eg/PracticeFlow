import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../../lib/api";
import type { ManagementGroup } from "../../types/api";
import { showToast } from "../../lib/toast";

export function GroupAssignments({ groups }: { groups: ManagementGroup[] }) {
  const queryClient = useQueryClient();
  const remove = useMutation({ mutationFn: async ({ groupId, teacherId }: { groupId: string; teacherId: string }) => api.delete(`/management/groups/${groupId}/teachers/${teacherId}`), onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ["management", "groups"] }); showToast("Преподаватель снят с группы"); } });
  return <div><header className="mb-5"><h2 className="font-display text-xl font-bold text-[var(--color-ink)]">Закрепление преподавателей</h2><p className="mt-1 text-sm text-[var(--color-muted)]">Назначение добавляется на вкладке «Группы». Здесь можно безопасно снять ненужное закрепление.</p></header><div className="grid gap-4 md:grid-cols-2">{groups.map((group) => <section key={group.id} className="card p-5"><div className="flex justify-between"><p className="font-mono-code text-lg font-semibold text-[var(--color-ink)]">{group.name}</p><span className="text-xs text-[var(--color-muted)]">{group.student_count} студентов</span></div><div className="mt-4 space-y-2">{group.teacher_ids.length === 0 && <p className="text-sm text-[var(--color-muted)]">Преподаватель не назначен.</p>}{group.teacher_ids.map((teacherId, index) => <div key={teacherId} className="flex items-center justify-between rounded-xl bg-[var(--color-surface)] px-3 py-2.5"><span className="text-sm text-[var(--color-ink-soft)]">{group.teacher_names[index] ?? "Преподаватель"}</span><button onClick={() => { if (window.confirm(`Снять преподавателя с группы ${group.name}?`)) remove.mutate({ groupId: group.id, teacherId }); }} className="btn btn-ghost px-2 py-1 text-xs text-[var(--color-danger-500)]">Снять</button></div>)}</div></section>)}</div></div>;
}
