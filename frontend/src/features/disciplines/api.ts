import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { DEFAULT_PAGE_SIZE, paginationFromResponse, withPagination } from "../../lib/pagination";
import { useAuth } from "../auth/useAuth";
import type { Discipline, DisciplineGroup, DisciplineInput, TeachingMaterial, Topic, TopicInput } from "./types";

export const MAX_MATERIAL_BYTES = 20 * 1024 * 1024;

function useScope() {
  const { user } = useAuth();
  return { key: ["curriculum", user?.organization_id, user?.user_id] as const, enabled: user?.role === "TEACHER" };
}

async function page<T>(path: string, offset: number, signal: AbortSignal) {
  const requested = { offset, limit: DEFAULT_PAGE_SIZE };
  const response = await api.get<T[]>(withPagination(path, requested), { signal });
  return { items: response.data, ...paginationFromResponse(response, requested, response.data.length) };
}

export function useDisciplines(offset = 0, archived = false) {
  const scope = useScope();
  return useQuery({ queryKey: [...scope.key, "disciplines", { offset, archived }], enabled: scope.enabled,
    queryFn: ({ signal }) => page<Discipline>(`/disciplines?archived=${archived}`, offset, signal) });
}

export function useDiscipline(id: string) {
  const scope = useScope();
  return useQuery({ queryKey: [...scope.key, "discipline", id], enabled: scope.enabled && !!id,
    queryFn: async ({ signal }) => (await api.get<Discipline>(`/disciplines/${id}`, { signal })).data });
}

export function useDisciplineGroups(id: string, enabled = true) {
  const scope = useScope();
  return useQuery({ queryKey: [...scope.key, "discipline", id, "groups"], enabled: scope.enabled && !!id && enabled,
    queryFn: async ({ signal }) => (await api.get<DisciplineGroup[]>(`/disciplines/${id}/groups`, { signal })).data });
}

export function useAvailableGroups(offset = 0) {
  const scope = useScope();
  return useQuery({ queryKey: [...scope.key, "available-groups", offset], enabled: scope.enabled,
    queryFn: ({ signal }) => page<DisciplineGroup>("/groups", offset, signal) });
}

export function useTopics(id: string, offset = 0, archived = false, enabled = true) {
  const scope = useScope();
  return useQuery({ queryKey: [...scope.key, "discipline", id, "topics", { offset, archived }],
    enabled: scope.enabled && !!id && enabled,
    queryFn: ({ signal }) => page<Topic>(`/disciplines/${id}/topics?archived=${archived}`, offset, signal) });
}

export function useTopic(id: string) {
  const scope = useScope();
  return useQuery({ queryKey: [...scope.key, "topic", id], enabled: scope.enabled && !!id,
    queryFn: async ({ signal }) => (await api.get<Topic>(`/topics/${id}`, { signal })).data });
}

export function useMaterials(id: string, offset = 0, enabled = true) {
  const scope = useScope();
  return useQuery({ queryKey: [...scope.key, "topic", id, "materials", { offset }], enabled: scope.enabled && !!id && enabled,
    queryFn: ({ signal }) => page<TeachingMaterial>(`/topics/${id}/materials`, offset, signal) });
}

export function useSaveDiscipline(id?: string) {
  const client = useQueryClient();
  const scope = useScope();
  return useMutation({ retry: false,
    mutationFn: async (value: DisciplineInput | { is_archived: boolean }) =>
      id ? (await api.patch<Discipline>(`/disciplines/${id}`, value)).data
        : (await api.post<Discipline>("/disciplines", value)).data,
    onSuccess: async () => { await client.invalidateQueries({ queryKey: scope.key }); } });
}

export function useSaveTopic(disciplineId: string, id?: string) {
  const client = useQueryClient();
  const scope = useScope();
  return useMutation({ retry: false,
    mutationFn: async (value: TopicInput | { is_archived: boolean }) =>
      id ? (await api.patch<Topic>(`/topics/${id}`, value)).data
        : (await api.post<Topic>(`/disciplines/${disciplineId}/topics`, value)).data,
    onSuccess: async () => { await client.invalidateQueries({ queryKey: scope.key }); } });
}

export function useUploadMaterial(topicId: string) {
  const client = useQueryClient();
  const scope = useScope();
  return useMutation({ retry: false,
    mutationFn: async ({ file, title, key }: { file: File; title: string; key: string }) => {
      const body = new FormData();
      body.append("file", file);
      if (title.trim()) body.append("title", title.trim());
      return (await api.post<TeachingMaterial>(`/topics/${topicId}/materials`, body, {
        headers: { "Idempotency-Key": key },
      })).data;
    },
    onSuccess: async () => { await client.invalidateQueries({ queryKey: [...scope.key, "topic", topicId, "materials"] }); } });
}

export function useDeleteMaterial(topicId: string) {
  const client = useQueryClient();
  const scope = useScope();
  return useMutation({ retry: false, mutationFn: async (id: string) => { await api.delete(`/materials/${id}`); },
    onSettled: async () => { await client.invalidateQueries({ queryKey: [...scope.key, "topic", topicId, "materials"] }); } });
}

export async function downloadMaterial(material: TeachingMaterial) {
  const response = await api.get<Blob>(`/materials/${material.id}/download`, { responseType: "blob" });
  const objectUrl = URL.createObjectURL(response.data);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = material.original_filename;
  document.body.appendChild(link);
  try { link.click(); } finally { link.remove(); window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000); }
}
