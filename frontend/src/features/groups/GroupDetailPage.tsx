import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeftIcon } from "@heroicons/react/24/outline";
import { useTranslation } from "react-i18next";
import { GroupCodeChip } from "../../components/GroupCodeChip";
import { useAddStudent, useAvailableStudents, useBulkRemoveStudents, useBulkTransferStudents, useGroupDetail, useMyGroups, useRemoveStudent, useTransferStudent } from "./api";
import { showToast } from "../../lib/toast";
import { ErrorState, LoadingState } from "../../components/ui/StateViews";
import { PaginationControls } from "../../components/ui/PaginationControls";
import { useLocaleFormatters } from "../../i18n/formatters";
import type { BulkStudentOperationResult, GroupMemberOut } from "../../types/api";

type BulkAction = { kind: "remove" } | { kind: "transfer"; targetGroupId: string; targetGroupName: string };

interface BulkOperationSummary {
  action: BulkAction["kind"];
  targetGroupName?: string;
  succeeded: Array<{ studentId: string; name: string }>;
  failed: Array<{ studentId: string; name: string; code: string }>;
}

export function GroupDetailPage() {
  const { t } = useTranslation(["groups", "common"]);
  const { formatNumber } = useLocaleFormatters();
  const { groupId } = useParams<{ groupId: string }>();
  const [studentOffset, setStudentOffset] = useState(0);
  const [availableStudentOffset, setAvailableStudentOffset] = useState(0);
  const [availableStudentSearch, setAvailableStudentSearch] = useState("");

  const groupQuery = useGroupDetail(groupId, studentOffset);
  const availableStudentsQuery = useAvailableStudents(groupId, availableStudentOffset, availableStudentSearch);
  const addStudent = useAddStudent(groupId!);
  const [studentToAdd, setStudentToAdd] = useState("");
  const [transferTargets, setTransferTargets] = useState<Record<string, string>>({});
  const [selectedStudentIds, setSelectedStudentIds] = useState<string[]>([]);
  const [bulkTransferTarget, setBulkTransferTarget] = useState("");
  const [bulkAction, setBulkAction] = useState<BulkAction | null>(null);
  const [bulkResult, setBulkResult] = useState<BulkOperationSummary | null>(null);
  const allGroupsQuery = useMyGroups();
  const removeStudent = useRemoveStudent(groupId!);
  const transferStudent = useTransferStudent(groupId!);
  const bulkRemoveStudents = useBulkRemoveStudents(groupId!);
  const bulkTransferStudents = useBulkTransferStudents(groupId!);

  const group = groupQuery.data?.data;
  const studentPagination = groupQuery.data?.pagination;
  const availableStudents = availableStudentsQuery.data?.items ?? [];
  const allGroups = allGroupsQuery.data?.items ?? [];

  if (groupQuery.isLoading) return <LoadingState label={t("loadingGroup")} />;
  if (groupQuery.isError) return <ErrorState error={groupQuery.error} onRetry={() => void groupQuery.refetch()} />;
  if (!group) return <ErrorState message={t("groupUnavailable")} onRetry={() => void groupQuery.refetch()} />;

  const selectedStudentIdSet = new Set(selectedStudentIds);
  const selectedStudents = group.students.filter((student) => selectedStudentIdSet.has(student.student_id));
  const selectedCount = selectedStudents.length;
  const allVisibleStudentsSelected = group.students.length > 0 && selectedCount === group.students.length;
  const selectedTargetGroup = allGroups.find((item) => item.id === bulkTransferTarget);
  const bulkPending = bulkRemoveStudents.isPending || bulkTransferStudents.isPending;

  const toggleStudentSelection = (studentId: string, checked: boolean) => {
    setSelectedStudentIds((current) => checked ? [...new Set([...current, studentId])] : current.filter((id) => id !== studentId));
    setBulkResult(null);
  };
  const toggleVisibleStudentSelection = (checked: boolean) => {
    setSelectedStudentIds(checked ? group.students.map((student) => student.student_id) : []);
    setBulkResult(null);
  };
  const changeStudentPage = (offset: number) => {
    setStudentOffset(offset);
    setSelectedStudentIds([]);
    setBulkResult(null);
  };
  const storeBulkResult = (action: BulkAction, result: BulkStudentOperationResult) => {
    const names = new Map(group.students.map((student) => [student.student_id, student.full_name]));
    setBulkResult({
      action: action.kind,
      targetGroupName: action.kind === "transfer" ? action.targetGroupName : undefined,
      succeeded: result.succeeded_student_ids.map((studentId) => ({ studentId, name: names.get(studentId) ?? studentId })),
      failed: result.failed.map((failure) => ({ studentId: failure.student_id, name: names.get(failure.student_id) ?? failure.student_id, code: failure.code })),
    });
    setSelectedStudentIds(result.failed.map((failure) => failure.student_id));
    setBulkAction(null);
    if (result.succeeded_student_ids.length > 0) showToast(t(action.kind === "remove" ? "bulkRemoveCompleted" : "bulkTransferCompleted", { count: result.succeeded_student_ids.length }));
  };
  const confirmBulkAction = () => {
    if (!bulkAction) return;
    const studentIds = selectedStudents.map((student) => student.student_id);
    if (bulkAction.kind === "remove") {
      bulkRemoveStudents.mutate(studentIds, { onSuccess: (result) => storeBulkResult(bulkAction, result) });
      return;
    }
    bulkTransferStudents.mutate({ studentIds, targetGroupId: bulkAction.targetGroupId }, { onSuccess: (result) => storeBulkResult(bulkAction, result) });
  };

  return (
    <div>
      <Link to="/groups" className="inline-flex items-center gap-1.5 text-sm font-semibold text-[var(--color-muted)] hover:text-[var(--color-brand-600)]">
        <ArrowLeftIcon className="size-4" />{t("backToGroups")}
      </Link>

      <header className="mt-4 mb-6 flex flex-wrap items-center justify-between gap-4 border-b border-[var(--color-border)] pb-5">
        <div className="flex items-center gap-3">
          <GroupCodeChip code={group.name} size="md" />
          <div>
            <p className="page-kicker">{t("academicGroup")}</p>
            <h1 className="font-display text-xl font-extrabold text-[var(--color-ink)]">{group.academic_year}</h1>
          </div>
        </div>
        <span className="rounded-[5px] border border-[var(--color-border)] bg-white px-3 py-1.5 text-xs font-semibold text-[var(--color-ink-soft)]">
          {t("students")} ({formatNumber(studentPagination?.total ?? group.students.length)})
        </span>
      </header>

      <div className="table-frame">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--color-border)] px-5 py-3">
          <p className="text-sm font-medium text-[var(--color-ink)]">{t("groupMembers")}</p>
          <div className="flex flex-wrap gap-2"><input value={availableStudentSearch} onChange={(event) => { setAvailableStudentSearch(event.target.value); setAvailableStudentOffset(0); }} className="input max-w-52 py-2" aria-label={t("searchAvailableStudent")} placeholder={t("studentSearchPlaceholder")} />{availableStudents.length > 0 && <><select value={studentToAdd} onChange={(e) => setStudentToAdd(e.target.value)} className="input max-w-60 py-2"><option value="">{t("addStudent")}</option>{availableStudents.map((student) => <option key={student.id} value={student.id}>{student.full_name}</option>)}</select><button disabled={!studentToAdd || addStudent.isPending} onClick={() => addStudent.mutate(studentToAdd, { onSuccess: () => setStudentToAdd("") })} className="btn btn-primary px-3">{t("common:add")}</button></>}</div>
        </div>
        {availableStudentsQuery.isError && <div className="p-4"><ErrorState compact error={availableStudentsQuery.error} message={t("loadStudentsError")} onRetry={() => void availableStudentsQuery.refetch()} /></div>}
        {allGroupsQuery.isError && <div className="p-4"><ErrorState compact error={allGroupsQuery.error} message={t("loadTransferGroupsError")} onRetry={() => void allGroupsQuery.refetch()} /></div>}
        {group.students.length > 0 && <div className="flex flex-wrap items-center gap-2 border-b border-[var(--color-border)] bg-[var(--color-surface)] px-5 py-3">
          <p className="mr-auto text-sm font-medium text-[var(--color-ink-soft)]" aria-live="polite">{t("selectedStudentsCount", { count: selectedCount })}</p>
          <label className="sr-only" htmlFor="bulk-transfer-target">{t("bulkTransferTarget")}</label>
          <select id="bulk-transfer-target" aria-label={t("bulkTransferTarget")} value={bulkTransferTarget} onChange={(event) => setBulkTransferTarget(event.target.value)} className="input max-w-60 py-2 text-sm">
            <option value="">{t("bulkTransferTarget")}</option>
            {allGroups.filter((item) => item.id !== group.id).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
          <button disabled={selectedCount === 0 || !selectedTargetGroup || bulkPending} onClick={() => selectedTargetGroup && setBulkAction({ kind: "transfer", targetGroupId: selectedTargetGroup.id, targetGroupName: selectedTargetGroup.name })} className="btn btn-secondary px-3 py-2">{t("bulkTransfer")}</button>
          <button disabled={selectedCount === 0 || bulkPending} onClick={() => setBulkAction({ kind: "remove" })} className="btn btn-danger px-3 py-2">{t("bulkRemove")}</button>
        </div>}
        {(bulkRemoveStudents.isError || bulkTransferStudents.isError) && <p className="mx-5 mt-4 rounded-xl bg-[var(--color-danger-50)] px-3 py-2 text-sm font-medium text-[var(--color-danger-500)]" role="alert">{t("bulkOperationFailed")}</p>}
        {bulkResult && <BulkOperationResultSummary summary={bulkResult} />}
        {group.students.length === 0 ? (
          <EmptyState text={t("noStudents")} />
        ) : (
          <table className="table-base">
            <thead>
              <tr>
                <th className="w-12 px-5 py-3"><input type="checkbox" aria-label={t("selectAllStudents")} checked={allVisibleStudentsSelected} onChange={(event) => toggleVisibleStudentSelection(event.target.checked)} /></th>
                <th className="px-5 py-3 font-medium">{t("common:fullName")}</th>
                <th className="px-5 py-3 font-medium">{t("common:email")}</th>
                <th className="px-5 py-3 text-right font-medium">{t("common:actions")}</th>
              </tr>
            </thead>
            <tbody>
              {group.students.map((student) => (
              <tr key={student.id}>
                <td className="px-5 py-3"><input type="checkbox" aria-label={t("selectStudent", { name: student.full_name })} checked={selectedStudentIdSet.has(student.student_id)} onChange={(event) => toggleStudentSelection(student.student_id, event.target.checked)} /></td>
                <td className="px-5 py-3 text-[var(--color-ink)]">{student.full_name}</td>
                <td className="px-5 py-3 text-[var(--color-muted)]">{student.email}</td>
                <td className="px-5 py-3"><div className="flex flex-wrap items-center justify-end gap-2"><select value={transferTargets[student.student_id] ?? ""} onChange={(e) => setTransferTargets({ ...transferTargets, [student.student_id]: e.target.value })} className="rounded border border-[var(--color-border)] bg-white px-2 py-1 text-xs"><option value="">{t("transferStudent")}</option>{allGroups.filter((item) => item.id !== group.id).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select><button disabled={!transferTargets[student.student_id] || transferStudent.isPending} onClick={() => { const targetGroupId = transferTargets[student.student_id]; if (targetGroupId && window.confirm(t("transferConfirm", { name: student.full_name }))) transferStudent.mutate({ studentId: student.student_id, targetGroupId }, { onSuccess: () => showToast(t("studentTransferred")) }); }} className="text-xs font-medium text-[var(--color-brand-600)] disabled:opacity-50">{t("common:confirm")}</button><button onClick={() => { if (window.confirm(t("removeStudentConfirm", { name: student.full_name }))) removeStudent.mutate(student.student_id, { onSuccess: () => showToast(t("studentRemoved")) }); }} className="text-xs font-medium text-[var(--color-danger-500)]">{t("common:delete")}</button></div></td>
              </tr>
              ))}
            </tbody>
          </table>
        )}
        {studentPagination && <div className="px-5 pb-4"><PaginationControls pagination={studentPagination} onPageChange={changeStudentPage} isFetching={groupQuery.isFetching} label={t("students")} /></div>}
        {availableStudentsQuery.data && <div className="px-5 pb-4"><PaginationControls pagination={availableStudentsQuery.data} onPageChange={setAvailableStudentOffset} isFetching={availableStudentsQuery.isFetching} label={t("availableStudents")} /></div>}
      </div>

      {bulkAction && <BulkStudentActionDialog action={bulkAction} students={selectedStudents} isPending={bulkPending} onCancel={() => setBulkAction(null)} onConfirm={confirmBulkAction} />}
    </div>
  );
}

function BulkStudentActionDialog({ action, students, isPending, onCancel, onConfirm }: { action: BulkAction; students: GroupMemberOut[]; isPending: boolean; onCancel: () => void; onConfirm: () => void }) {
  const { t } = useTranslation(["groups", "common"]);
  const isRemoval = action.kind === "remove";
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" role="presentation">
      <section className="card w-full max-w-md p-6" role="dialog" aria-modal="true" aria-labelledby="bulk-student-action-title">
        <h2 id="bulk-student-action-title" className="font-display text-xl font-bold text-[var(--color-ink)]">{t(isRemoval ? "bulkRemoveConfirmTitle" : "bulkTransferConfirmTitle")}</h2>
        <p className="mt-3 text-sm leading-6 text-[var(--color-ink-soft)]">{t(isRemoval ? "bulkRemoveConfirmDescription" : "bulkTransferConfirmDescription", { count: students.length, group: action.kind === "transfer" ? action.targetGroupName : "" })}</p>
        <ul className="mt-3 max-h-32 list-disc overflow-y-auto pl-5 text-sm text-[var(--color-muted)]">
          {students.map((student) => <li key={student.student_id}>{student.full_name}</li>)}
        </ul>
        <div className="mt-6 flex justify-end gap-2">
          <button type="button" onClick={onCancel} disabled={isPending} className="btn btn-secondary">{t("common:cancel")}</button>
          <button type="button" onClick={onConfirm} disabled={isPending} className={isRemoval ? "btn btn-danger" : "btn btn-primary"}>{isPending ? t("bulkProcessing") : t(isRemoval ? "bulkRemove" : "bulkTransfer")}</button>
        </div>
      </section>
    </div>
  );
}

function BulkOperationResultSummary({ summary }: { summary: BulkOperationSummary }) {
  const { t } = useTranslation("groups");
  return (
    <section className="mx-5 mt-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4" aria-live="polite">
      <p className="text-sm font-semibold text-[var(--color-ink)]">{t("bulkOperationSummary", { succeeded: summary.succeeded.length, failed: summary.failed.length })}</p>
      {summary.succeeded.length > 0 && <div className="mt-3"><p className="text-sm font-medium text-[var(--color-success-500)]">{t("bulkSucceeded")}</p><ul className="mt-1 list-disc pl-5 text-sm text-[var(--color-ink-soft)]">{summary.succeeded.map((student) => <li key={student.studentId}>{student.name}</li>)}</ul></div>}
      {summary.failed.length > 0 && <div className="mt-3"><p className="text-sm font-medium text-[var(--color-danger-500)]">{t("bulkFailed")}</p><ul className="mt-1 list-disc pl-5 text-sm text-[var(--color-ink-soft)]">{summary.failed.map((student) => <li key={student.studentId}>{student.name}: {t(`bulkFailure.${student.code}` as never, { defaultValue: t("bulkFailure.UNKNOWN") })}</li>)}</ul></div>}
    </section>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="empty-state">
      <p className="text-sm text-[var(--color-muted)]">{text}</p>
    </div>
  );
}
