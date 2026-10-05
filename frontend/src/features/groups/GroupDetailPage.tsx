import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { GroupCodeChip } from "../../components/GroupCodeChip";
import { StatusBadge } from "../../components/StatusBadge";
import { useAddStudent, useAvailableStudents, useBulkRemoveStudents, useBulkTransferStudents, useCloseInternship, useGroupDetail, useGroupInternships, useGroupProgress, useGroupReviewQueue, useMyGroups, usePublishInternship, useRemoveStudent, useTransferStudent, useUpdateInternship } from "./api";
import { showToast } from "../../lib/toast";
import { CreateInternshipDialog } from "./CreateInternshipDialog";
import { ArrowLeftIcon, CalendarDaysIcon, PlusIcon } from "@heroicons/react/24/outline";
import { ErrorState, LoadingState } from "../../components/ui/StateViews";
import { PaginationControls } from "../../components/ui/PaginationControls";
import { useTranslation } from "react-i18next";
import { useLocaleFormatters } from "../../i18n/formatters";
import type { BulkStudentOperationResult, GroupMemberOut } from "../../types/api";
import { useProductFeatures } from "../auth/useProductFeatures";

type Tab = "students" | "internships" | "reports";
const REVIEW_QUEUE_STATUSES = ["DRAFT", "SUBMITTED", "UNDER_REVIEW", "REVISION_REQUIRED", "APPROVED", "LOCKED"] as const;

type BulkAction = { kind: "remove" } | { kind: "transfer"; targetGroupId: string; targetGroupName: string };

interface BulkOperationSummary {
  action: BulkAction["kind"];
  targetGroupName?: string;
  succeeded: Array<{ studentId: string; name: string }>;
  failed: Array<{ studentId: string; name: string; code: string }>;
}

export function GroupDetailPage() {
  const { t } = useTranslation(["groups", "common", "reports"]);
  const { formatDate, formatNumber } = useLocaleFormatters();
  const { legacy_document_editor_enabled: legacyDocumentEditorEnabled } = useProductFeatures();
  const { groupId } = useParams<{ groupId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const initialTab = searchParams.get("tab");
  const [activeTab, setActiveTab] = useState<Tab>(
    initialTab === "students" || initialTab === "reports"
      ? initialTab
      : "internships",
  );
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [studentOffset, setStudentOffset] = useState(0);
  const [internshipOffset, setInternshipOffset] = useState(0);
  const [availableStudentOffset, setAvailableStudentOffset] = useState(0);
  const [availableStudentSearch, setAvailableStudentSearch] = useState("");

  const groupQuery = useGroupDetail(groupId, studentOffset);
  const internshipsQuery = useGroupInternships(groupId, internshipOffset);
  const internshipOptionsQuery = useGroupInternships(groupId, 0, 200);
  const deadlineParam = searchParams.get("deadline");
  const reviewQueueQuery = useGroupReviewQueue(groupId, {
    status: searchParams.get("status") ?? undefined,
    internshipId: searchParams.get("internship_id") ?? undefined,
    deadline: deadlineParam === "overdue" || deadlineParam === "due_today" || deadlineParam === "due_soon" || deadlineParam === "upcoming" ? deadlineParam : undefined,
    student: searchParams.get("student") ?? undefined,
  }, Number(searchParams.get("offset")) > 0 ? Number(searchParams.get("offset")) : 0);
  const availableStudentsQuery = useAvailableStudents(groupId, availableStudentOffset, availableStudentSearch);
  const addStudent = useAddStudent(groupId!);
  const publishInternship = usePublishInternship(groupId!);
  const [studentToAdd, setStudentToAdd] = useState("");
  const [transferTargets, setTransferTargets] = useState<Record<string, string>>({});
  const [selectedStudentIds, setSelectedStudentIds] = useState<string[]>([]);
  const [bulkTransferTarget, setBulkTransferTarget] = useState("");
  const [bulkAction, setBulkAction] = useState<BulkAction | null>(null);
  const [bulkResult, setBulkResult] = useState<BulkOperationSummary | null>(null);
  const [editingInternship, setEditingInternship] = useState<string | null>(null);
  const allGroupsQuery = useMyGroups();
  const progressQuery = useGroupProgress(groupId);
  const removeStudent = useRemoveStudent(groupId!);
  const transferStudent = useTransferStudent(groupId!);
  const bulkRemoveStudents = useBulkRemoveStudents(groupId!);
  const bulkTransferStudents = useBulkTransferStudents(groupId!);
  const updateInternship = useUpdateInternship(groupId!);
  const closeInternship = useCloseInternship(groupId!);

  const group = groupQuery.data?.data;
  const studentPagination = groupQuery.data?.pagination;
  const internships = internshipsQuery.data?.items ?? [];
  const reports = reviewQueueQuery.data?.items ?? [];
  const internshipOptions = internshipOptionsQuery.data?.items ?? [];
  const availableStudents = availableStudentsQuery.data?.items ?? [];
  const allGroups = allGroupsQuery.data?.items ?? [];
  const progress = progressQuery.data;

  const setTab = (tab: Tab) => {
    setActiveTab(tab);
    const next = new URLSearchParams(searchParams);
    if (tab === "internships") next.delete("tab");
    else next.set("tab", tab);
    setSearchParams(next);
  };
  const setQueueParam = (key: "status" | "internship_id" | "deadline" | "student", value: string) => {
    const next = new URLSearchParams(searchParams);
    next.set("tab", "reports");
    if (value) next.set(key, value);
    else next.delete(key);
    next.delete("offset");
    setSearchParams(next);
  };
  const setQueueOffset = (offset: number) => {
    const next = new URLSearchParams(searchParams);
    if (offset > 0) next.set("offset", String(offset));
    else next.delete("offset");
    setSearchParams(next);
  };

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
          <div><p className="page-kicker">{t("academicGroup")}</p><h1 className="font-display text-xl font-extrabold text-[var(--color-ink)]">{group.academic_year}</h1></div>
        </div>
        {activeTab === "internships" && legacyDocumentEditorEnabled && (
          <button
            onClick={() => setIsCreateOpen(true)}
            className="btn btn-primary"
          >
            <PlusIcon className="size-4" />{t("createInternship")}
          </button>
        )}
      </header>

      <div className="mb-6 flex gap-1 overflow-x-auto border-b border-[var(--color-border)]">
        <TabButton active={activeTab === "internships"} onClick={() => setTab("internships")}>
          {t("internships")}
        </TabButton>
        <TabButton active={activeTab === "students"} onClick={() => setTab("students")}>
          {t("students")} ({formatNumber(studentPagination?.total ?? group.students.length)})
        </TabButton>
        <TabButton active={activeTab === "reports"} onClick={() => setTab("reports")}>
          {t("reports")}
        </TabButton>
      </div>

      {progressQuery.isError && <div className="mb-6"><ErrorState compact error={progressQuery.error} message={t("loadProgressError")} onRetry={() => void progressQuery.refetch()} /></div>}
      {progress && <div className="section-panel mb-6 grid grid-cols-2 overflow-hidden sm:grid-cols-3 lg:grid-cols-6">{[[t("progressTotal"), progress.total, "text-[var(--color-ink)]"], [t("progressDraft"), progress.draft, "text-[var(--color-muted)]"], [t("progressSubmitted"), progress.submitted, "text-[var(--color-amber-500)]"], [t("progressUnderReview"), progress.under_review, "text-[var(--color-amber-500)]"], [t("progressRevision"), progress.revision_required, "text-[var(--color-danger-500)]"], [t("progressLocked"), progress.locked, "text-[var(--color-success-500)]"]].map(([label, value, color]) => <div key={String(label)} className="border-b border-r border-[var(--color-border)] bg-white px-4 py-3 last:border-r-0 lg:border-b-0"><p className="text-xs font-semibold text-[var(--color-muted)]">{label}</p><p className={`mt-1 font-display text-2xl font-bold tracking-[-0.03em] ${color}`}>{formatNumber(Number(value))}</p></div>)}</div>}

      {activeTab === "students" && (
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
      )}

      {activeTab === "internships" && (
        <div className="space-y-3">
          {internshipsQuery.isLoading && <LoadingState label={t("loadingInternships")} />}
          {internshipsQuery.isError && <ErrorState error={internshipsQuery.error} onRetry={() => void internshipsQuery.refetch()} />}
          {!internshipsQuery.isLoading && !internshipsQuery.isError && internships?.length === 0 && (
            <EmptyState text={t("internshipsEmpty")} />
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
              <p className="mt-3 flex items-center gap-1.5 text-xs font-medium text-[var(--color-muted)]"><CalendarDaysIcon className="size-3.5" />{formatDate(internship.start_date)} — {formatDate(internship.end_date)} · {t("deadlineLabel", { date: formatDate(internship.deadline) })}</p>
              {legacyDocumentEditorEnabled && internship.status === "DRAFT" && <div className="mt-4 border-t border-[var(--color-border)] pt-3"><div className="flex flex-wrap gap-2"><button onClick={() => publishInternship.mutate(internship.id, { onSuccess: () => showToast(t("internshipPublished")) })} disabled={publishInternship.isPending} className="btn btn-primary px-3 py-2">{t("publishAndAssign")}</button><button onClick={() => setEditingInternship(editingInternship === internship.id ? null : internship.id)} className="btn btn-secondary px-3 py-2">{t("common:edit")}</button></div>{editingInternship === internship.id && <InternshipEditForm internship={internship} onCancel={() => setEditingInternship(null)} onSave={(payload) => updateInternship.mutate({ internshipId: internship.id, ...payload }, { onSuccess: () => { setEditingInternship(null); showToast(t("internshipUpdated")); } })} saving={updateInternship.isPending} />}</div>}
              {internship.status === "PUBLISHED" && <div className="mt-4 border-t border-[var(--color-border)] pt-3"><button onClick={() => { if (window.confirm(t("closeInternshipConfirm"))) closeInternship.mutate(internship.id, { onSuccess: () => showToast(t("internshipClosed")) }); }} disabled={closeInternship.isPending} className="btn btn-danger px-3 py-2">{t("closeInternship")}</button></div>}
            </div>
          ))}
          {!internshipsQuery.isError && internshipsQuery.data && <PaginationControls pagination={internshipsQuery.data} onPageChange={setInternshipOffset} isFetching={internshipsQuery.isFetching} label={t("internships")} />}
        </div>
      )}

      {activeTab === "reports" && (
        <div className="space-y-4">
          <div className="card grid gap-3 p-4 md:grid-cols-2 xl:grid-cols-4">
            <label className="text-sm font-medium text-[var(--color-ink-soft)]">{t("reports:queueStatusFilter")}<select aria-label={t("reports:queueStatusFilter")} value={searchParams.get("status") ?? ""} onChange={(event) => setQueueParam("status", event.target.value)} className="input mt-1 w-full py-2"><option value="">{t("reports:queueAllStatuses")}</option>{REVIEW_QUEUE_STATUSES.map((status) => <option key={status} value={status}>{t(`common:statuses.${status}` as never)}</option>)}</select></label>
            <label className="text-sm font-medium text-[var(--color-ink-soft)]">{t("reports:queueInternshipFilter")}<select aria-label={t("reports:queueInternshipFilter")} value={searchParams.get("internship_id") ?? ""} onChange={(event) => setQueueParam("internship_id", event.target.value)} className="input mt-1 w-full py-2"><option value="">{t("reports:queueAllInternships")}</option>{internshipOptions.map((internship) => <option key={internship.id} value={internship.id}>{internship.title}</option>)}</select></label>
            <label className="text-sm font-medium text-[var(--color-ink-soft)]">{t("reports:queueDeadlineFilter")}<select aria-label={t("reports:queueDeadlineFilter")} value={deadlineParam ?? ""} onChange={(event) => setQueueParam("deadline", event.target.value)} className="input mt-1 w-full py-2"><option value="">{t("reports:queueAllDeadlines")}</option><option value="overdue">{t("reports:queueDeadlineOverdue")}</option><option value="due_today">{t("reports:queueDeadlineToday")}</option><option value="due_soon">{t("reports:queueDeadlineSoon")}</option><option value="upcoming">{t("reports:queueDeadlineUpcoming")}</option></select></label>
            <label className="text-sm font-medium text-[var(--color-ink-soft)]">{t("reports:queueStudentFilter")}<input aria-label={t("reports:queueStudentFilter")} value={searchParams.get("student") ?? ""} onChange={(event) => setQueueParam("student", event.target.value)} className="input mt-1 w-full py-2" placeholder={t("reports:queueStudentPlaceholder")} /></label>
          </div>
          {reviewQueueQuery.isLoading && <LoadingState label={t("loadingReports")} />}
          {reviewQueueQuery.isError && <ErrorState error={reviewQueueQuery.error} onRetry={() => void reviewQueueQuery.refetch()} />}
          {!reviewQueueQuery.isLoading && !reviewQueueQuery.isError && reports.length === 0 && <EmptyState text={t("reports:queueEmpty")} />}
          {!reviewQueueQuery.isError && reports.map((report) => (
            <Link
              key={report.id}
              to={`/groups/${groupId}/reports/${report.id}${searchParams.toString() ? `?${searchParams.toString()}` : ""}`}
              className="card flex flex-wrap items-center justify-between gap-3 px-4 py-3 transition-colors hover:border-[var(--color-brand-100)]"
            >
              <span><span className="block text-sm font-medium text-[var(--color-ink)]">{report.student_name}</span><span className="mt-0.5 block text-sm text-[var(--color-ink-soft)]">{report.internship_title}</span><span className="mt-1 block text-xs text-[var(--color-muted)]">{t("reports:deadlineLabel", { date: formatDate(report.deadline) })}{report.is_overdue && <span className="ml-2 font-semibold text-[var(--color-danger-500)]">{t("reports:deadlineStates.overdue")}</span>}{report.submitted_late && <span className="ml-2 font-semibold text-[var(--color-amber-500)]">{t("reports:queueSubmittedLate")}</span>}{report.open_comments_count > 0 && <span className="ml-2">{t("reports:queueOpenComments", { count: report.open_comments_count })}</span>}</span></span>
              <span className="flex items-center gap-3"><span className="font-mono-code text-xs text-[var(--color-muted)]">#{report.id.slice(0, 8)} · {t("openReview")}</span><StatusBadge status={report.status} /></span>
            </Link>
          ))}
          {!reviewQueueQuery.isError && reviewQueueQuery.data && <PaginationControls pagination={reviewQueueQuery.data} onPageChange={setQueueOffset} isFetching={reviewQueueQuery.isFetching} label={t("reports")} />}
        </div>
      )}

      {legacyDocumentEditorEnabled && isCreateOpen && group && <CreateInternshipDialog groupId={group.id} onClose={() => setIsCreateOpen(false)} />}
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
  const { t } = useTranslation(["groups", "common"]);
  const [title, setTitle] = useState(internship.title); const [description, setDescription] = useState(internship.description ?? ""); const [startDate, setStartDate] = useState(internship.start_date); const [endDate, setEndDate] = useState(internship.end_date); const [deadline, setDeadline] = useState(internship.deadline);
  return <form onSubmit={(e) => { e.preventDefault(); onSave({ title, description, start_date: startDate, end_date: endDate, deadline }); }} className="mt-4 grid gap-3 rounded-xl bg-[var(--color-surface)] p-4 md:grid-cols-3"><input value={title} onChange={(e) => setTitle(e.target.value)} className="input md:col-span-2" required /><input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="input" required /><textarea value={description} onChange={(e) => setDescription(e.target.value)} className="input min-h-18 resize-y md:col-span-2" placeholder={t("descriptionPlaceholder")} /><div className="grid grid-cols-2 gap-2"><input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="input" required /><input type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)} className="input" required /></div><div className="flex justify-end gap-2 md:col-span-3"><button type="button" onClick={onCancel} className="btn btn-ghost">{t("common:cancel")}</button><button disabled={saving} className="btn btn-primary">{t("common:save")}</button></div></form>;
}
