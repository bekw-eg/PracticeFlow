import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { DEFAULT_PAGE_SIZE, fetchPage } from "../../lib/pagination";
import type { DocumentCheckFinding, DocumentCheckJob, DocumentRunDetail, DocumentSettings, DocumentLifecycle, LocalPlagiarismMatch, LocalPlagiarismRun, ParagraphClassification, TeacherDocumentPreview, TeacherDocumentSubmission } from "../../types/api";

const base = "/document-checks";

export function useDocumentSettings(submissionId: string | undefined) {
  return useQuery({
    queryKey: ["document-settings", submissionId],
    queryFn: async ({ signal }) => (await api.get<DocumentSettings>(`${base}/teacher/submissions/${submissionId}/settings`, { signal })).data,
    enabled: !!submissionId,
  });
}

export function useDocumentParagraphs(submissionId: string | undefined, enabled = true) {
  return useQuery({
    queryKey: ["document-paragraphs", submissionId],
    queryFn: async ({ signal }) => (await api.get<ParagraphClassification[]>(`${base}/teacher/submissions/${submissionId}/paragraphs`, { signal })).data,
    enabled: !!submissionId && enabled,
    staleTime: 5 * 60_000,
  });
}

export function useSaveDocumentSettings(submissionId: string) {
  const client = useQueryClient();
  return useMutation({
    retry: false,
    mutationFn: async (draft: DocumentSettings) => (await api.put<DocumentSettings>(`${base}/teacher/submissions/${submissionId}/settings`, {
      revision: draft.revision, rules: draft.rules, paragraph_overrides: draft.paragraph_overrides,
    })).data,
    onSuccess: async (saved) => {
      await client.cancelQueries({ queryKey: ["document-settings", submissionId] });
      client.setQueryData(["document-settings", submissionId], saved);
      void client.invalidateQueries({ queryKey: ["document-paragraphs", submissionId] });
    },
  });
}

export function useRecheckDocument(submissionId: string) {
  const client = useQueryClient();
  return useMutation({
    retry: false,
    mutationFn: async ({ revision, idempotencyKey }: { revision: number; idempotencyKey: string }) =>
      (await api.post<DocumentCheckJob>(`${base}/teacher/submissions/${submissionId}/recheck`, { revision }, {
        headers: { "Idempotency-Key": idempotencyKey },
      })).data,
    onSuccess: async (job) => {
      await client.cancelQueries({ queryKey: ["teacher-document-submission", submissionId] });
      client.setQueryData<TeacherDocumentSubmission>(["teacher-document-submission", submissionId], (current) =>
        current && (current.job.run_number ?? 1) <= (job.run_number ?? 1) ? { ...current, job } : current);
      void client.invalidateQueries({ queryKey: ["teacher-document-submission", submissionId] });
      void client.invalidateQueries({ queryKey: ["teacher-document-submissions"] });
      void client.invalidateQueries({ queryKey: ["document-runs", submissionId] });
    },
  });
}

export function useDocumentRuns(submissionId: string | undefined, latestJobId?: string, latestStatus?: string) {
  return useQuery({
    queryKey: ["document-runs", submissionId, latestJobId, latestStatus],
    queryFn: async ({ signal }) => {
      const items: DocumentCheckJob[] = [];
      for (let offset = 0; ; offset += 100) {
        signal.throwIfAborted();
        const page = await fetchPage<DocumentCheckJob>(`${base}/teacher/submissions/${submissionId}/runs`, { offset, limit: 100 });
        signal.throwIfAborted();
        items.push(...page.items);
        if (!page.hasMore || !page.items.length) return items;
      }
    },
    enabled: !!submissionId,
    refetchInterval: (query) => query.state.data?.some(job => job.status === "QUEUED" || job.status === "PROCESSING") ? 2_000 : false,
  });
}

export function useDocumentRun(submissionId: string | undefined, jobId: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ["document-run", submissionId, jobId],
    queryFn: async ({ signal }) => (await api.get<DocumentRunDetail>(`${base}/teacher/submissions/${submissionId}/runs/${jobId}`, { signal })).data,
    enabled: !!submissionId && !!jobId && enabled,
  });
}

export function useAllSubmissionFindings(submissionId: string, enabled: boolean, jobId?: string) {
  return useQuery({
    queryKey: ["document-check-findings", "teacher", submissionId, "all", jobId],
    queryFn: async ({ signal }) => {
      const items: DocumentCheckFinding[] = [];
      // Load every page so highlights remain visible when the sidebar changes page.
      for (let offset = 0; ; offset += 100) {
        signal.throwIfAborted();
        const page = await fetchPage<DocumentCheckFinding>(`${base}/teacher/submissions/${submissionId}/findings${jobId ? `?job_id=${jobId}` : ""}`, { offset, limit: 100 });
        signal.throwIfAborted();
        items.push(...page.items);
        if (!page.hasMore || !page.items.length) return items;
      }
    },
    enabled,
  });
}

export function useLocalPlagiarismRuns(submissionId: string | undefined, latestJobId?: string, latestStatus?: string) {
  return useQuery({
    queryKey: ["local-plagiarism-runs", submissionId, latestJobId, latestStatus],
    queryFn: async ({ signal }) => {
      const items: LocalPlagiarismRun[] = [];
      for (let offset = 0; ; offset += 100) {
        signal.throwIfAborted();
        const page = await fetchPage<LocalPlagiarismRun>(`${base}/teacher/submissions/${submissionId}/plagiarism-runs`, { offset, limit: 100 });
        signal.throwIfAborted();
        items.push(...page.items);
        if (!page.hasMore || !page.items.length) return items;
      }
    },
    enabled: !!submissionId,
    refetchInterval: (query) => query.state.data?.some(run => run.status === "QUEUED" || run.status === "PROCESSING") ? 2_000 : false,
  });
}

export function useAllLocalPlagiarismMatches(submissionId: string, runId: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ["local-plagiarism-matches", submissionId, runId, "all"],
    queryFn: async ({ signal }) => {
      const items: LocalPlagiarismMatch[] = [];
      for (let offset = 0; ; offset += 100) {
        signal.throwIfAborted();
        const page = await fetchPage<LocalPlagiarismMatch>(`${base}/teacher/submissions/${submissionId}/plagiarism-runs/${runId}/matches`, { offset, limit: 100 });
        signal.throwIfAborted();
        items.push(...page.items);
        if (!page.hasMore || !page.items.length) return items;
      }
    },
    enabled: !!submissionId && !!runId && enabled,
  });
}

export function useSubmissionFindings(submissionId: string, enabled: boolean, offset = 0, limit = 25, jobId?: string) {
  return useQuery({
    queryKey: ["document-check-findings", "teacher", submissionId, jobId, { offset, limit }],
    queryFn: () => fetchPage<DocumentCheckFinding>(`${base}/teacher/submissions/${submissionId}/findings${jobId ? `?job_id=${jobId}` : ""}`, {
      offset, limit,
    }),
    enabled,
  });
}

export function useTeacherDocumentSubmission(submissionId: string | undefined) {
  return useQuery({
    queryKey: ["teacher-document-submission", submissionId],
    queryFn: async ({ signal }) => (await api.get<TeacherDocumentSubmission>(`${base}/teacher/submissions/${submissionId}`, { signal })).data,
    enabled: !!submissionId,
    refetchInterval: (query) => {
      const status = query.state.data?.job.status;
      return status === "QUEUED" || status === "PROCESSING" ? 2_000 : 10_000;
    },
  });
}

export function useTeacherDocumentPreview(submissionId: string | undefined, enabled = true) {
  return useQuery({
    queryKey: ["teacher-document-preview", submissionId],
    queryFn: async () => (await api.get<TeacherDocumentPreview>(`${base}/teacher/submissions/${submissionId}/preview`)).data,
    enabled: !!submissionId && enabled,
    staleTime: 5 * 60_000,
  });
}

export function useTeacherDocumentSubmissions(offset = 0, archived = false) {
  return useQuery({
    queryKey: ["teacher-document-submissions", { offset, archived }],
    queryFn: () => fetchPage<TeacherDocumentSubmission>(`${base}/teacher/submissions?archived=${archived ? "true" : "false"}`, { offset, limit: DEFAULT_PAGE_SIZE }),
    refetchInterval: (query) => query.state.data?.items.some(
      (submission) => submission.job.status === "QUEUED" || submission.job.status === "PROCESSING",
    ) ? 2_000 : false,
  });
}

export function useUpdateDocumentLifecycle(submissionId: string) {
  const client = useQueryClient();
  return useMutation({
    retry: false,
    mutationFn: async (value: Pick<DocumentLifecycle, "revision" | "archived" | "disclosure_allowed">) =>
      (await api.put<TeacherDocumentSubmission>(`${base}/teacher/submissions/${submissionId}/lifecycle`, value)).data,
    onSuccess: async (saved) => {
      client.setQueryData(["teacher-document-submission", submissionId], saved);
      await client.invalidateQueries({ queryKey: ["teacher-document-submissions"] });
      void client.invalidateQueries({ queryKey: ["local-plagiarism-matches", submissionId] });
    },
  });
}

export function useDeleteDocumentOriginal(submissionId: string) {
  const client = useQueryClient();
  return useMutation({
    retry: false,
    mutationFn: async (revision: number) =>
      (await api.delete<TeacherDocumentSubmission>(`${base}/teacher/submissions/${submissionId}/original`, { data: { revision } })).data,
    onSuccess: async (saved) => {
      client.setQueryData(["teacher-document-submission", submissionId], saved);
      client.removeQueries({ queryKey: ["teacher-document-preview", submissionId] });
      client.removeQueries({ queryKey: ["document-paragraphs", submissionId] });
      await client.invalidateQueries({ queryKey: ["teacher-document-submissions"] });
    },
    onSettled: () => { void client.invalidateQueries({ queryKey: ["teacher-document-submission", submissionId] }); },
  });
}

export function useUploadTeacherDocumentSubmission() {
  const client = useQueryClient();
  return useMutation({
    retry: false,
    mutationFn: async ({ file, profileVersionId, studentLabel, plagiarismSourceDisclosureAllowed, idempotencyKey, groupId, workTitle, workType }: {
      file: File;
      profileVersionId: string;
      studentLabel?: string;
      groupId?: string;
      workTitle?: string;
      workType?: "COURSEWORK" | "REPORT";
      plagiarismSourceDisclosureAllowed?: boolean;
      idempotencyKey: string;
    }) => {
      const body = new FormData();
      body.append("file", file);
      if (groupId) body.append("review_group_id", groupId);
      if (workTitle) body.append("work_title", workTitle.trim());
      if (workType) body.append("work_type", workType);
      body.append("profile_version_id", profileVersionId);
      if (studentLabel?.trim()) body.append("student_label", studentLabel.trim());
      body.append("plagiarism_source_disclosure_allowed", String(plagiarismSourceDisclosureAllowed ?? false));
      return (await api.post<TeacherDocumentSubmission>(`${base}/teacher/submissions`, body, {
        headers: { "Idempotency-Key": idempotencyKey },
      })).data;
    },
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["teacher-document-submissions"] });
      void client.invalidateQueries({ queryKey: ["review-groups"] });
    },
  });
}

export async function downloadTeacherSubmissionOriginal(submission: TeacherDocumentSubmission) {
  const response = await api.get<Blob>(`${base}/teacher/submissions/${submission.id}/original`, { responseType: "blob" });
  const objectUrl = URL.createObjectURL(response.data);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = submission.original_filename;
  document.body.appendChild(link);
  try {
    link.click();
  } finally {
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
  }
}
