import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { DEFAULT_PAGE_SIZE, fetchPage } from "../../lib/pagination";
import type { CheckProfile, CheckProfileVersion, CheckRule } from "../../types/api";

export function useCheckProfiles(offset = 0, limit = DEFAULT_PAGE_SIZE) {
  return useQuery({
    queryKey: ["check-profiles", { offset, limit }],
    queryFn: () => fetchPage<CheckProfile>("/check-profiles", { offset, limit }),
  });
}

export function useCheckProfile(profileId: string | undefined) {
  return useQuery({
    queryKey: ["check-profiles", profileId],
    queryFn: async () => (await api.get<CheckProfile>(`/check-profiles/${profileId}`)).data,
    enabled: !!profileId,
  });
}

export function useCheckProfileVersion(profileId: string | undefined, versionId: string | undefined) {
  return useQuery({
    queryKey: ["check-profiles", profileId, "versions", versionId],
    queryFn: async () => (await api.get<CheckProfileVersion>(`/check-profiles/${profileId}/versions/${versionId}`)).data,
    enabled: !!profileId && !!versionId,
  });
}

export function useCreateCheckProfile() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { name: string; description?: string }) => (await api.post<CheckProfile>("/check-profiles", payload)).data,
    onSuccess: () => void client.invalidateQueries({ queryKey: ["check-profiles"] }),
  });
}

export function useCreateCheckProfileVersion(profileId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (sourceVersionId?: string) => (await api.post<CheckProfileVersion>(`/check-profiles/${profileId}/versions`, sourceVersionId ? { source_version_id: sourceVersionId } : {})).data,
    onSuccess: () => void client.invalidateQueries({ queryKey: ["check-profiles"] }),
  });
}

export function useReplaceCheckRules(profileId: string, versionId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (rules: CheckRule[]) => (await api.put<CheckProfileVersion>(`/check-profiles/${profileId}/versions/${versionId}/rules`, { rules: rules.map(({ id: _id, ...rule }) => rule) })).data,
    onSuccess: (version) => {
      client.setQueryData(["check-profiles", profileId, "versions", version.id], version);
      void client.invalidateQueries({ queryKey: ["check-profiles"] });
    },
  });
}

export function useProfileVersionAction(profileId: string, versionId: string, action: "publish" | "retire") {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async () => (await api.post<CheckProfileVersion>(`/check-profiles/${profileId}/versions/${versionId}/${action}`)).data,
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["check-profiles"] });
      void client.invalidateQueries({ queryKey: ["check-profiles", profileId, "versions", versionId] });
    },
  });
}
