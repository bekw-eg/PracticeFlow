import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { DEFAULT_PAGE_SIZE, fetchPage } from "../../lib/pagination";
import type { CheckProfile, CheckRuleType, TeacherDocumentSubmission, TeacherReview } from "../../types/api";

export interface ReviewGroup { id: string; name: string; description: string | null; created_at: string; updated_at: string }
export interface GroupSummary {
  total_works: number; pending_works: number; reviewed_works: number; included_works: number; truncated_works: number;
  violations: { rule_type: CheckRuleType; violations_count: number; works_count: number }[];
}
const base = "/document-checks/teacher/groups";

export function useReviewGroups(offset: number) {
  return useQuery({ queryKey: ["review-groups", "list", offset], queryFn: () => fetchPage<ReviewGroup>(base, { offset }) });
}
export function useReviewGroup(id: string) {
  return useQuery({ queryKey: ["review-groups", id], queryFn: async ({ signal }) => (await api.get<ReviewGroup>(`${base}/${id}`, { signal })).data });
}
export function useSaveReviewGroup(id?: string) {
  const client = useQueryClient();
  return useMutation({ mutationFn: async (value: { name: string; description: string | null }) =>
    (await (id ? api.put<ReviewGroup>(`${base}/${id}`, value) : api.post<ReviewGroup>(base, value))).data,
    onSuccess: () => { void client.invalidateQueries({ queryKey: ["review-groups"] }); },
  });
}
export function useGroupWorks(id: string, offset: number, status: string) {
  return useQuery({ queryKey: ["review-groups", id, "works", offset, status],
    queryFn: () => fetchPage<TeacherDocumentSubmission>(`${base}/${id}/works${status ? `?review_status=${status}` : ""}`, { offset, limit: DEFAULT_PAGE_SIZE }),
    refetchInterval: 5_000,
  });
}
export function useGroupSummary(id: string) {
  return useQuery({ queryKey: ["review-groups", id, "summary"],
    queryFn: async ({ signal }) => (await api.get<GroupSummary>(`${base}/${id}/summary`, { signal })).data,
    refetchInterval: 5_000,
  });
}
export function useSaveTeacherReview(id: string) {
  const client = useQueryClient();
  return useMutation({ retry: false,
    mutationFn: async (value: { revision: number; remarks: string; job_id?: string }) => {
      const path = `/document-checks/teacher/submissions/${id}/review`;
      return (await (value.job_id ? api.post<TeacherReview>(`${path}/complete`, value) : api.put<TeacherReview>(path, value))).data;
    },
    onSuccess: async (review) => {
      await client.cancelQueries({ queryKey: ["teacher-document-submission", id] });
      client.setQueryData<TeacherDocumentSubmission>(["teacher-document-submission", id], current => current ? { ...current, teacher_review: review } : current);
      void client.invalidateQueries({ queryKey: ["teacher-document-submission", id] });
      void client.invalidateQueries({ queryKey: ["teacher-document-submissions"] });
      void client.invalidateQueries({ queryKey: ["review-groups"] });
    },
  });
}

export function usePublishedProfileOptions() {
  return useQuery({ queryKey: ["check-profiles", "upload-options"], queryFn: async ({ signal }) => {
    const items: CheckProfile[] = [];
    for (let offset = 0; ; offset += 100) {
      signal.throwIfAborted();
      const page = await fetchPage<CheckProfile>("/check-profiles", { offset, limit: 100 });
      items.push(...page.items);
      if (!page.hasMore || !page.items.length) return { items };
    }
  } });
}
