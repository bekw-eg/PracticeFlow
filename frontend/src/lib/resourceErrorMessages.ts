import { getApiErrorPresentation } from "./apiError";

export function uploadErrorMessage(error: unknown): string {
  return getApiErrorPresentation(error, "files").description;
}

export function exportErrorMessage(error: unknown): string {
  return getApiErrorPresentation(error, "export").description;
}
