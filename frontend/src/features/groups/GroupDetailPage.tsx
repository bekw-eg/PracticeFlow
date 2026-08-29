import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { GroupCodeChip } from "../../components/GroupCodeChip";
import { StatusBadge } from "../../components/StatusBadge";
import { useAddStudent, useAvailableStudents, useCloseInternship, useGroupDetail, useGroupInternships, useGroupProgress, useGroupReports, useMyGroups, usePublishInternship, useRemoveStudent, useTransferStudent, useUpdateInternship } from "./api";
import { showToast } from "../../lib/toast";
import { CreateInternshipDialog } from "./CreateInternshipDialog";
import { ArrowLeftIcon, CalendarDaysIcon, PlusIcon } from "@heroicons/react/24/outline";
import { ErrorState, LoadingState } from "../../components/ui/StateViews";
import { PaginationControls } from "../../components/ui/PaginationControls";

type Tab = "students" | "internships" | "reports";

export function GroupDetailPage() {
  const { groupId } = useParams<{ groupId: string }>();
  const [activeTab, setActiveTab] = useState<Tab>("internships");
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [studentOffset, setStudentOffset] = useState(0);
  const [internshipOffset, setInternshipOffset] = useState(0);
  const [reportOffset, setReportOffset] = useState(0);
  const [availableStudentOffset, setAvailableStudentOffset] = useState(0);
  const [availableStudentSearch, setAvailableStudentSearch] = useState("");

  const groupQuery = useGroupDetail(groupId, studentOffset);
  const internshipsQuery = useGroupInternships(groupId, internshipOffset);
  const reportsQuery = useGroupReports(groupId, reportOffset);
  const availableStudentsQuery = useAvailableStudents(groupId, availableStudentOffset, availableStudentSearch);
  const addStudent = useAddStudent(groupId!);
  const publishInternship = usePublishInternship(groupId!);
  const [studentToAdd, setStudentToAdd] = useState("");
  const [transferTargets, setTransferTargets] = useState<Record<string, string>>({});
  const [editingInternship, setEditingInternship] = useState<string | null>(null);
  const allGroupsQuery = useMyGroups();
  const progressQuery = useGroupProgress(groupId);
  const removeStudent = useRemoveStudent(groupId!);
  const transferStudent = useTransferStudent(groupId!);
  const updateInternship = useUpdateInternship(groupId!);
  const closeInternship = useCloseInternship(groupId!);

  const group = groupQuery.data?.data;
  const studentPagination = groupQuery.data?.pagination;
  const internships = internshipsQuery.data?.items ?? [];
  const reports = reportsQuery.data?.items ?? [];
  const availableStudents = availableStudentsQuery.data?.items ?? [];
  const allGroups = allGroupsQuery.data?.items ?? [];
  const progress = progressQuery.data;

  if (groupQuery.isLoading) return <LoadingState label="Загрузка группы…" />;
  if (groupQuery.isError) return <ErrorState error={groupQuery.error} onRetry={() => void groupQuery.refetch()} />;
  if (!group) return <ErrorState message="Группа не вернула данные. Повторите попытку." onRetry={() => void groupQuery.refetch()} />;

  return (
    <div>
      <Link to="/groups" className="inline-flex items-center gap-1.5 text-sm font-semibold text-[var(--color-muted)] hover:text-[var(--color-brand-600)]">
        <ArrowLeftIcon className="size-4" />Мои группы
      </Link>

      <header className="mt-4 mb-6 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <GroupCodeChip code={group.name} size="md" />
          <div><p className="page-kicker">Академическая группа</p><h1 className="font-display text-xl font-extrabold text-[var(--color-ink)]">{group.academic_year}</h1></div>
        </div>
        {activeTab === "internships" && (
          <button
            onClick={() => setIsCreateOpen(true)}
            className="btn btn-primary"
          >
            <PlusIcon className="size-4" />Практика
          </button>
        )}
      </header>

      <div className="mb-6 flex gap-1 overflow-x-auto border-b border-[var(--color-border)]">
        <TabButton active={activeTab === "internships"} onClick={() => setActiveTab("internships")}>
          Практики
        </TabButton>
        <TabButton active={activeTab === "students"} onClick={() => setActiveTab("students")}>
          Студенты ({studentPagination?.total ?? group.students.length})
        </TabButton>
        <TabButton active={activeTab === "reports"} onClick={() => setActiveTab("reports")}>
          Отчёты
        </TabButton>
      </div>

      {progressQuery.isError && <div className="mb-6"><ErrorState compact error={progressQuery.error} message="Не удалось загрузить сводку по отчётам." onRetry={() => void progressQuery.refetch()} /></div>}
      {progress && <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">{[["Всего", progress.total, "text-[var(--color-ink)]"], ["Черновики", progress.draft, "text-[var(--color-muted)]"], ["Отправлены", progress.submitted, "text-[var(--color-amber-500)]"], ["На проверке", progress.under_review, "text-[var(--color-amber-500)]"], ["Доработка", progress.revision_required, "text-[var(--color-danger-500)]"], ["Закрыты", progress.locked, "text-[var(--color-success-500)]"]].map(([label, value, color]) => <div key={String(label)} className="card px-4 py-3"><p className="text-xs font-semibold text-[var(--color-muted)]">{label}</p><p className={`mt-1 font-display text-2xl font-extrabold ${color}`}>{value}</p></div>)}</div>}

      {activeTab === "students" && (
        <div className="table-frame">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--color-border)] px-5 py-3">
            <p className="text-sm font-medium text-[var(--color-ink)]">Состав группы</p>
            <div className="flex flex-wrap gap-2"><input value={availableStudentSearch} onChange={(event) => { setAvailableStudentSearch(event.target.value); setAvailableStudentOffset(0); }} className="input max-w-52 py-2" aria-label="Поиск доступного студента" placeholder="Поиск студента…" />{availableStudents.length > 0 && <><select value={studentToAdd} onChange={(e) => setStudentToAdd(e.target.value)} className="input max-w-60 py-2"><option value="">Добавить студента…</option>{availableStudents.map((student) => <option key={student.id} value={student.id}>{student.full_name}</option>)}</select><button disabled={!studentToAdd || addStudent.isPending} onClick={() => addStudent.mutate(studentToAdd, { onSuccess: () => setStudentToAdd("") })} className="btn btn-primary px-3">Добавить</button></>}</div>
          </div>
          {availableStudentsQuery.isError && <div className="p-4"><ErrorState compact error={availableStudentsQuery.error} message="Не удалось загрузить список доступных студентов." onRetry={() => void availableStudentsQuery.refetch()} /></div>}
          {allGroupsQuery.isError && <div className="p-4"><ErrorState compact error={allGroupsQuery.error} message="Не удалось загрузить список групп для перевода студентов." onRetry={() => void allGroupsQuery.refetch()} /></div>}
          {group.students.length === 0 ? (
            <EmptyState text="В группе пока нет студентов." />
          ) : (
            <table className="table-base">
              <thead>
                <tr>
                  <th className="px-5 py-3 font-medium">Имя</th>
                  <th className="px-5 py-3 font-medium">Email</th>
                  <th className="px-5 py-3 text-right font-medium">Действия</th>
                </tr>
              </thead>
              <tbody>
                {group.students.map((student) => (
                <tr key={student.id}>
                  <td className="px-5 py-3 text-[var(--color-ink)]">{student.full_name}</td>
                  <td className="px-5 py-3 text-[var(--color-muted)]">{student.email}</td>
                  <td className="px-5 py-3"><div className="flex flex-wrap items-center justify-end gap-2"><select value={transferTargets[student.student_id] ?? ""} onChange={(e) => setTransferTargets({ ...transferTargets, [student.student_id]: e.target.value })} className="rounded border border-[var(--color-border)] bg-white px-2 py-1 text-xs"><option value="">Перевести…</option>{allGroups.filter((item) => item.id !== group.id).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select><button disabled={!transferTargets[student.student_id] || transferStudent.isPending} onClick={() => { const targetGroupId = transferTargets[student.student_id]; if (targetGroupId && window.confirm(`Перевести ${student.full_name}?`)) transferStudent.mutate({ studentId: student.student_id, targetGroupId }, { onSuccess: () => showToast("Студент переведён") }); }} className="text-xs font-medium text-[var(--color-brand-600)] disabled:opacity-50">ОК</button><button onClick={() => { if (window.confirm(`Удалить ${student.full_name} из группы? Уже созданные отчёты сохранятся.`)) removeStudent.mutate(student.student_id, { onSuccess: () => showToast("Студент удалён из состава") }); }} className="text-xs font-medium text-[var(--color-danger-500)]">Удалить</button></div></td>
                </tr>
                ))}
              </tbody>
            </table>
          )}
          {studentPagination && <div className="px-5 pb-4"><PaginationControls pagination={studentPagination} onPageChange={setStudentOffset} isFetching={groupQuery.isFetching} label="Студенты" /></div>}
          {availableStudentsQuery.data && <div className="px-5 pb-4"><PaginationControls pagination={availableStudentsQuery.data} onPageChange={setAvailableStudentOffset} isFetching={availableStudentsQuery.isFetching} label="Доступные студенты" /></div>}
        </div>
      )}

      {activeTab === "internships" && (
        <div className="space-y-3">
          {internshipsQuery.isLoading && <LoadingState label="Загрузка практик…" />}
          {internshipsQuery.isError && <ErrorState error={internshipsQuery.error} onRetry={() => void internshipsQuery.refetch()} />}
          {!internshipsQuery.isLoading && !internshipsQuery.isError && internships?.length === 0 && (
            <EmptyState text="В этой группе ещё нет практик. Создайте первую, используя новый или существующий шаблон." />
          )}
          {!internshipsQuery.isError && internships?.map((internship) => (
            <div key={internship.id} className="card p-5">
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="font-medium text-[var(--color-ink)]">{internship.title}</h3>
                  {internship.description && <p className="mt-1 text-sm text-[var(--color-muted)]">{internship.description}</p>}
                </div>
                <StatusBadge status={internship.status} />
              </div>
              <p className="mt-3 flex items-center gap-1.5 text-xs font-medium text-[var(--color-muted)]"><CalendarDaysIcon className="size-3.5" />{internship.start_date} — {internship.end_date} · Дедлайн: {internship.deadline}</p>
              {internship.status === "DRAFT" && <div className="mt-4 border-t border-[var(--color-border)] pt-3"><div className="flex flex-wrap gap-2"><button onClick={() => publishInternship.mutate(internship.id, { onSuccess: () => showToast("Практика опубликована, отчёты назначены") })} disabled={publishInternship.isPending} className="btn btn-primary px-3 py-2">Опубликовать и назначить группе</button><button onClick={() => setEditingInternship(editingInternship === internship.id ? null : internship.id)} className="btn btn-secondary px-3 py-2">Редактировать</button></div>{editingInternship === internship.id && <InternshipEditForm internship={internship} onCancel={() => setEditingInternship(null)} onSave={(payload) => updateInternship.mutate({ internshipId: internship.id, ...payload }, { onSuccess: () => { setEditingInternship(null); showToast("Черновик практики обновлён"); } })} saving={updateInternship.isPending} />}</div>}
              {internship.status === "PUBLISHED" && <div className="mt-4 border-t border-[var(--color-border)] pt-3"><button onClick={() => { if (window.confirm("Закрыть практику? После этого её нельзя будет снова открыть.")) closeInternship.mutate(internship.id, { onSuccess: () => showToast("Практика закрыта") }); }} disabled={closeInternship.isPending} className="btn btn-danger px-3 py-2">Закрыть практику</button></div>}
            </div>
          ))}
          {!internshipsQuery.isError && internshipsQuery.data && <PaginationControls pagination={internshipsQuery.data} onPageChange={setInternshipOffset} isFetching={internshipsQuery.isFetching} label="Практики" />}
        </div>
      )}

      {activeTab === "reports" && (
        <div className="space-y-2">
          {reportsQuery.isLoading && <LoadingState label="Загрузка отчётов…" />}
          {reportsQuery.isError && <ErrorState error={reportsQuery.error} onRetry={() => void reportsQuery.refetch()} />}
          {!reportsQuery.isLoading && !reportsQuery.isError && reports?.length === 0 && <EmptyState text="Отчётов пока нет — они появятся после публикации практики." />}
          {!reportsQuery.isError && reports?.map((report) => (
            <Link
              key={report.id}
              to={`/groups/${groupId}/reports/${report.id}`}
              className="card flex items-center justify-between px-4 py-3 transition-colors hover:border-[var(--color-brand-100)]"
            >
              <span><span className="block text-sm font-medium text-[var(--color-ink)]">{group.students.find((student) => student.student_id === report.student_id)?.full_name ?? "Студент"}</span><span className="font-mono-code text-xs text-[var(--color-muted)]">#{report.id.slice(0, 8)} · открыть проверку</span></span>
              <StatusBadge status={report.status} />
            </Link>
          ))}
          {!reportsQuery.isError && reportsQuery.data && <PaginationControls pagination={reportsQuery.data} onPageChange={setReportOffset} isFetching={reportsQuery.isFetching} label="Отчёты" />}
        </div>
      )}

      {isCreateOpen && group && <CreateInternshipDialog groupId={group.id} onClose={() => setIsCreateOpen(false)} />}
    </div>
  );
}

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium transition-colors ${
        active
          ? "border-[var(--color-brand-500)] text-[var(--color-brand-700)]"
          : "border-transparent text-[var(--color-muted)] hover:text-[var(--color-ink-soft)]"
      }`}
    >
      {children}
    </button>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="empty-state">
      <p className="text-sm text-[var(--color-muted)]">{text}</p>
    </div>
  );
}

function InternshipEditForm({ internship, onSave, onCancel, saving }: { internship: { title: string; description: string | null; start_date: string; end_date: string; deadline: string }; onSave: (payload: { title: string; description: string; start_date: string; end_date: string; deadline: string }) => void; onCancel: () => void; saving: boolean }) {
  const [title, setTitle] = useState(internship.title); const [description, setDescription] = useState(internship.description ?? ""); const [startDate, setStartDate] = useState(internship.start_date); const [endDate, setEndDate] = useState(internship.end_date); const [deadline, setDeadline] = useState(internship.deadline);
  return <form onSubmit={(e) => { e.preventDefault(); onSave({ title, description, start_date: startDate, end_date: endDate, deadline }); }} className="mt-4 grid gap-3 rounded-xl bg-[var(--color-surface)] p-4 md:grid-cols-3"><input value={title} onChange={(e) => setTitle(e.target.value)} className="input md:col-span-2" required /><input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="input" required /><textarea value={description} onChange={(e) => setDescription(e.target.value)} className="input min-h-18 resize-y md:col-span-2" placeholder="Описание" /><div className="grid grid-cols-2 gap-2"><input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="input" required /><input type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)} className="input" required /></div><div className="flex justify-end gap-2 md:col-span-3"><button type="button" onClick={onCancel} className="btn btn-ghost">Отмена</button><button disabled={saving} className="btn btn-primary">Сохранить</button></div></form>;
}
