import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "../../lib/api";
import type { DocumentModel, ReportDocumentResponse, TemplateVersionDetail, UploadedFile, VariableCatalogEntry, Block } from "../../types/document";

export function useTemplateVersionDocument(templateId: string | undefined, versionId: string | undefined) {
  return useQuery({
    queryKey: ["templates", templateId, "versions", versionId, "document"],
    queryFn: async () => (await api.get<TemplateVersionDetail>(`/templates/${templateId}/versions/${versionId}/document`)).data,
    enabled: !!templateId && !!versionId,
    staleTime: Infinity,
  });
}

export function useSaveTemplateVersionDocument(templateId: string, versionId: string) {
  return useMutation({
    mutationFn: async ({ document, expectedRevision }: { document: DocumentModel; expectedRevision: number }) =>
      (await api.patch<TemplateVersionDetail>(`/templates/${templateId}/versions/${versionId}/document`, { document, expected_revision: expectedRevision })).data,
  });
}

export function useReportDocument(reportId: string | undefined) {
  return useQuery({
    queryKey: ["reports", reportId, "document"],
    queryFn: async () => (await api.get<ReportDocumentResponse>(`/reports/${reportId}/document`)).data,
    enabled: !!reportId,
    staleTime: Infinity,
  });
}

export function useSaveReportDocument(reportId: string) {
  return useMutation({
    mutationFn: async ({ sections, expectedRevision }: { sections: Record<string, Block[]>; expectedRevision: number }) =>
      (await api.patch<ReportDocumentResponse>(`/reports/${reportId}/document`, { sections, expected_revision: expectedRevision })).data,
  });
}

export function useVariableCatalog() {
  return useQuery({
    queryKey: ["variables", "catalog"],
    queryFn: async () => (await api.get<VariableCatalogEntry[]>("/variables/catalog")).data,
    staleTime: Infinity,
  });
}

export async function uploadImage(file: File): Promise<UploadedFile> {
  const formData = new FormData();
  formData.append("file", file);
  const { data } = await api.post<UploadedFile>("/files", formData);
  return data;
}
