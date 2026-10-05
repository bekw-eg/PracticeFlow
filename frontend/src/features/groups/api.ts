import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { DEFAULT_PAGE_SIZE, fetchPage, fetchPaginatedResource } from "../../lib/pagination";
import type { BulkStudentOperationResult, GroupDetail, GroupMemberOut, GroupReportProgress, GroupSummary, InternshipOut, ReportOut, ReviewQueueDeadlineFilter, StudentOptionOut, TeacherReviewQueueItem, TemplateOut } from "../../types/api";

export function useMyGroups(offset = 0) {
  return useQuery({
    queryKey: ["groups", { offset }],
    queryFn: () => fetchPage<GroupSummary>("/groups", { offset, limit: DEFAULT_PAGE_SIZE }),
  });
}

export function useGroupDetail(groupId: string | undefined, offset = 0) {
  return useQuery({
    queryKey: ["groups", groupId, "students", { offset }],
    queryFn: () => fetchPaginatedResource<GroupDetail>(`/groups/${groupId}`, { offset, limit: DEFAULT_PAGE_SIZE }),
    enabled: !!groupId,
  });
}

export function useGroupInternships(groupId: string | undefined, offset = 0, limit = DEFAULT_PAGE_SIZE) {
  return useQuery({
    queryKey: ["groups", groupId, "internships", { offset, limit }],
    queryFn: () => fetchPage<InternshipOut>(`/groups/${groupId}/internships`, { offset, limit }),
    enabled: !!groupId,
  });
}

export function useGroupReports(groupId: string | undefined, offset = 0) {
  return useQuery({
    queryKey: ["groups", groupId, "reports", { offset }],
    queryFn: () => fetchPage<ReportOut>(`/groups/${groupId}/reports`, { offset, limit: DEFAULT_PAGE_SIZE }),
    enabled: !!groupId,
  });
}

export interface ReviewQueueFilters {
  status?: string;
  internshipId?: string;
  deadline?: ReviewQueueDeadlineFilter;
  student?: string;
}

function reviewQueuePath(groupId: string, filters: ReviewQueueFilters): string {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.internshipId) params.set("internship_id", filters.internshipId);
  if (filters.deadline) params.set("deadline", filters.deadline);
  if (filters.student?.trim()) params.set("student", filters.student.trim());
  const query = params.toString();
  return `/groups/${groupId}/reports/queue${query ? `?${query}` : ""}`;
}

export function useGroupReviewQueue(groupId: string | undefined, filters: ReviewQueueFilters, offset = 0) {
  return useQuery({
    queryKey: ["groups", groupId, "review-queue", { ...filters, offset }],
    queryFn: () => fetchPage<TeacherReviewQueueItem>(reviewQueuePath(groupId!, filters), { offset, limit: DEFAULT_PAGE_SIZE }),
    enabled: !!groupId,
  });
}

export function useTemplates(offset = 0) {
  return useQuery({
    queryKey: ["templates", { offset }],
    queryFn: () => fetchPage<TemplateOut>("/templates", { offset, limit: DEFAULT_PAGE_SIZE }),
  });
}

interface CreateInternshipPayload {
  groupId: string;
  title: string;
  description?: string;
  template_version_id: string;
  start_date: string;
  end_date: string;
  deadline: string;
}

export function useCreateInternship() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ groupId, ...payload }: CreateInternshipPayload) =>
      (await api.post<InternshipOut>(`/groups/${groupId}/internships`, payload)).data,
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({ queryKey: ["groups", variables.groupId, "internships"] });
    },
  });
}

export function usePublishInternship(groupId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (internshipId: string) => (await api.post<InternshipOut>(`/internships/${internshipId}/publish`)).data,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["groups", groupId, "internships"] });
      void queryClient.invalidateQueries({ queryKey: ["groups", groupId, "reports"] });
    },
  });
}

export function useAvailableStudents(groupId: string | undefined, offset = 0, q?: string) {
  return useQuery({
    queryKey: ["groups", groupId, "available-students", { offset, q }],
    queryFn: () => fetchPage<StudentOptionOut>(`/groups/${groupId}/available-students`, { offset, limit: DEFAULT_PAGE_SIZE, q }),
    enabled: !!groupId,
  });
}

export function useAddStudent(groupId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (studentId: string) => (await api.post<GroupMemberOut>(`/groups/${groupId}/students`, { student_id: studentId })).data,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["groups", groupId] });
      void queryClient.invalidateQueries({ queryKey: ["groups", groupId, "available-students"] });
    },
  });
}

export function useRemoveStudent(groupId: string) {
  const queryClient = useQueryClient();
  return useMutation({ mutationFn: async (studentId: string) => api.delete(`/groups/${groupId}/students/${studentId}`), onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["groups", groupId] }) });
}

export function useTransferStudent(groupId: string) {
  const queryClient = useQueryClient();
  return useMutation({ mutationFn: async ({ studentId, targetGroupId }: { studentId: string; targetGroupId: string }) => api.post(`/groups/${groupId}/students/${studentId}/transfer/${targetGroupId}`), onSuccess: (_data, values) => { void queryClient.invalidateQueries({ queryKey: ["groups", groupId] }); void queryClient.invalidateQueries({ queryKey: ["groups", values.targetGroupId] }); void queryClient.invalidateQueries({ queryKey: ["groups"] }); } });
}

export function useBulkRemoveStudents(groupId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (studentIds: string[]) =>
      (await api.post<BulkStudentOperationResult>(`/groups/${groupId}/students/bulk-remove`, { student_ids: studentIds })).data,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["groups", groupId] });
      void queryClient.invalidateQueries({ queryKey: ["groups"] });
    },
  });
}

export function useBulkTransferStudents(groupId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ studentIds, targetGroupId }: { studentIds: string[]; targetGroupId: string }) =>
      (await api.post<BulkStudentOperationResult>(`/groups/${groupId}/students/bulk-transfer`, {
        student_ids: studentIds,
        target_group_id: targetGroupId,
      })).data,
    onSuccess: (_data, values) => {
      void queryClient.invalidateQueries({ queryKey: ["groups", groupId] });
      void queryClient.invalidateQueries({ queryKey: ["groups", values.targetGroupId] });
      void queryClient.invalidateQueries({ queryKey: ["groups"] });
    },
  });
}

export function useGroupProgress(groupId: string | undefined) {
  return useQuery({ queryKey: ["groups", groupId, "progress"], queryFn: async () => (await api.get<GroupReportProgress>(`/groups/${groupId}/report-progress`)).data, enabled: !!groupId });
}

export function useUpdateInternship(groupId: string) {
  const queryClient = useQueryClient();
  return useMutation({ mutationFn: async ({ internshipId, ...payload }: { internshipId: string; title?: string; description?: string; start_date?: string; end_date?: string; deadline?: string }) => api.patch<InternshipOut>(`/internships/${internshipId}`, payload), onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["groups", groupId, "internships"] }) });
}

export function useCloseInternship(groupId: string) {
  const queryClient = useQueryClient();
  return useMutation({ mutationFn: async (internshipId: string) => api.post<InternshipOut>(`/internships/${internshipId}/close`), onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["groups", groupId, "internships"] }) });
}
