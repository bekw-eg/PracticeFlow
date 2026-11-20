import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { DEFAULT_PAGE_SIZE, fetchPage, fetchPaginatedResource } from "../../lib/pagination";
import type { BulkStudentOperationResult, GroupDetail, GroupMemberOut, GroupSummary, StudentOptionOut } from "../../types/api";

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
