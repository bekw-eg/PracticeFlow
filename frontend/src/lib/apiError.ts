import { isAxiosError } from "axios";

import { i18n } from "../i18n";
import type { TranslationResources } from "../i18n/resources";

export type ApiErrorKind =
  | "payload-too-large"
  | "forbidden"
  | "not-found"
  | "conflict"
  | "rate-limited"
  | "server"
  | "network"
  | "unauthorized"
  | "validation"
  | "bad-request"
  | "unknown";

export type ApiErrorScope =
  | "auth"
  | "mfa"
  | "files"
  | "export"
  | "reports"
  | "comments"
  | "groups"
  | "internships"
  | "management"
  | "document"
  | "unknown";

export interface ApiErrorPresentation {
  kind: ApiErrorKind;
  title: string;
  description: string;
  status: number | null;
}

type ErrorLike = {
  response?: { status?: unknown; data?: unknown };
  status?: unknown;
  request?: unknown;
  code?: unknown;
  config?: { url?: unknown };
};

type ErrorObject = Record<string, unknown>;
type ValidationIssue = { loc?: unknown; type?: unknown };
type ErrorKey = keyof TranslationResources["errors"];

const detailMessageKeys: Record<string, ErrorKey> = {
  "upload user quota exceeded.": "storageQuota",
  "organization storage quota exceeded.": "storageQuota",
  "upload quota exceeded.": "storageQuota",
  "invalid credentials": "authInvalidCredentials",
  "this access link is invalid or has expired.": "authAccessLinkInvalid",
  "organization is not available to this user": "authOrganizationUnavailable",
  "invalid authentication code": "mfaInvalidCode",
  "mfa challenge is invalid": "mfaChallengeInvalid",
  "mfa challenge has expired": "mfaChallengeExpired",
  "mfa challenge is no longer valid": "mfaChallengeInvalid",
  "mfa is not available for this membership": "mfaUnavailable",
  "mfa is not available for this user": "mfaUnavailable",
  "this challenge is not an enrollment challenge": "mfaUnavailable",
  "start mfa enrollment before confirming it": "mfaUnavailable",
  "this challenge requires mfa enrollment": "mfaUnavailable",
  "mfa credential is not enrolled": "mfaUnavailable",
  "recovery is not available for this challenge": "mfaUnavailable",
  "this recovery request has not been approved": "mfaUnavailable",
  "peer recovery is available only to super admins": "mfaUnavailable",
  "a super admin cannot approve their own recovery": "mfaUnavailable",
  "unsupported image encoding.": "fileInvalid",
  "empty file.": "fileInvalid",
  "invalid or corrupt image file.": "fileInvalid",
  "image exceeds the configured file-size limit.": "uploadTooLarge",
  "file storage is temporarily unavailable. please try again later.": "fileStorageUnavailable",
  "report has no document content to export yet.": "exportDocumentUnavailable",
  "export is not ready for download.": "exportNotReady",
  "export has expired. create a new export to download it.": "exportExpired",
  "export file is no longer available.": "exportExpired",
  "export storage is temporarily unavailable. please try again later.": "exportUnavailable",
  "pdf export is unavailable because its native rendering dependencies are not installed.": "exportUnavailable",
  "export permission is no longer valid.": "exportUnavailable",
  "report is not currently editable": "reportNotEditable",
  "report document has not been initialized yet": "reportDocumentUnavailable",
  "report is not in a submittable state": "reportNotEditable",
  "comments can only be added while a report is under review.": "commentsUnavailable",
  "report has no submitted version to comment on.": "commentsUnavailable",
  "this report is not currently under review.": "commentsUnavailable",
  "only the root comment of a thread can be resolved.": "commentsUnavailable",
  "student already in group": "studentAlreadyInGroup",
  "student is already in the target group": "studentAlreadyInTargetGroup",
  "dates are inconsistent": "internshipDatesInvalid",
  "only a draft internship can be edited": "internshipNotDraft",
  "only a draft internship can be published": "internshipNotDraft",
  "only a published internship can be closed": "internshipNotPublished",
  "template version not found or not published": "templateVersionUnavailable",
  "password is required for a new user": "managementPasswordRequired",
  "this user is already a member of the organization": "managementMemberExists",
  "a group with this name already exists": "managementGroupExists",
  "department already exists": "managementUnavailable",
  "organization slug already exists": "managementUnavailable",
  "role catalog is not initialized": "managementUnavailable",
};

const machineCodeKeys: Record<string, ErrorKey> = {
  DOCX_EXTENSION: "docxExtension",
  DOCX_MACROS: "docxMacros",
  DOCX_ENCRYPTED: "docxEncrypted",
  DOCX_UNSAFE_ARCHIVE: "docxArchiveUnsafe",
  DOCX_TOO_MANY_ENTRIES: "docxArchiveLimit",
  DOCX_ARCHIVE_LIMIT: "docxArchiveLimit",
  DOCX_COMPRESSION_RATIO: "docxArchiveLimit",
  DOCX_INVALID: "docxInvalid",
  DOCX_UPLOAD_TOO_LARGE: "docxTooLarge",
  PROFILE_RULES_REQUIRED: "documentCheckRulesRequired",
  PREVIEW_UNAVAILABLE: "documentPreviewUnavailable",
  PREVIEW_INVALID: "documentPreviewInvalid",
  DOCUMENT_CHECK_ASSIGNMENT_CLOSED: "documentCheckClosed",
  DOCUMENT_CHECK_ASSIGNMENT_NOT_PUBLISHED: "documentCheckClosed",
  IDEMPOTENCY_KEY_CONFLICT: "submissionKeyConflict",
  STORAGE_UNAVAILABLE: "fileStorageUnavailable",
  STALE_DOCUMENT_REVISION: "staleDocumentConflict",
  DOCUMENT_LIFECYCLE_CONFLICT: "staleDocumentConflict",
  DOCUMENT_ORIGINAL_DELETED: "documentOriginalDeleted",
  DOCUMENT_CHECK_ACTIVE: "documentOriginalActive",
  DOCUMENT_REMOVAL_PENDING: "documentOriginalRemovalPending",
  DOCUMENT_SETTINGS_CONFLICT: "staleDocumentConflict",
  PARAGRAPH_INDEX_INVALID: "validationDocument",
  SUBMISSION_PERSISTENCE_UNAVAILABLE: "fileStorageUnavailable",
  IDEMPOTENCY_KEY_INVALID: "validationDocument",
  STUDENT_LABEL_INVALID: "validationDocument",
};

function asObject(value: unknown): ErrorObject | null {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? value as ErrorObject : null;
}

function statusFrom(error: unknown): number | null {
  if (isAxiosError(error)) return typeof error.response?.status === "number" ? error.response.status : null;
  const candidate = asObject(error) as ErrorLike | null;
  if (candidate && typeof candidate.response?.status === "number") return candidate.response.status;
  return candidate && typeof candidate.status === "number" ? candidate.status : null;
}

function responseDataFrom(error: unknown): unknown {
  if (isAxiosError(error)) return error.response?.data;
  const candidate = asObject(error) as ErrorLike | null;
  return candidate?.response?.data;
}

function requestUrlFrom(error: unknown): string {
  if (isAxiosError(error)) return typeof error.config?.url === "string" ? error.config.url : "";
  const candidate = asObject(error) as ErrorLike | null;
  return typeof candidate?.config?.url === "string" ? candidate.config.url : "";
}

function isNetworkError(error: unknown): boolean {
  if (isAxiosError(error)) return !error.response && Boolean(error.request || error.code === "ERR_NETWORK");
  const candidate = asObject(error) as ErrorLike | null;
  return Boolean(candidate && !candidate.response && (candidate.request || candidate.code === "ERR_NETWORK"));
}

function detailFrom(error: unknown): unknown {
  const data = asObject(responseDataFrom(error));
  return data?.detail;
}

function machineCodeFrom(error: unknown): string | null {
  const detail = asObject(detailFrom(error));
  return typeof detail?.code === "string" ? detail.code : null;
}

function validationIssueFrom(error: unknown): ValidationIssue | null {
  const detail = detailFrom(error);
  if (!Array.isArray(detail)) return null;
  const first = asObject(detail[0]);
  return first ? { loc: first.loc, type: first.type } : null;
}

function fieldFromLocation(location: unknown): string | null {
  if (!Array.isArray(location)) return null;
  const field = [...location].reverse().find((part) => typeof part === "string");
  return typeof field === "string" ? field : null;
}

function validationMessageKey(error: unknown, scope: ApiErrorScope): ErrorKey {
  const issue = validationIssueFrom(error);
  const field = fieldFromLocation(issue?.loc);
  const type = typeof issue?.type === "string" ? issue.type : "";
  if (type === "missing") return "validationRequired";
  if (field === "email") return "validationEmail";
  if (field === "password") return "validationPassword";
  if (field === "code" || field === "challenge_id") return "validationMfaCode";
  if (field === "file") return "validationFile";
  if (scope === "document" || scope === "reports" || scope === "export") return "validationDocument";
  return "validationInvalid";
}

function detailMessageKey(error: unknown, scope: ApiErrorScope, status: number | null): ErrorKey | null {
  const machineCode = machineCodeFrom(error);
  if (machineCode && machineCodeKeys[machineCode]) return machineCodeKeys[machineCode];

  const detail = detailFrom(error);
  if (typeof detail === "string") {
    const exact = detailMessageKeys[detail.trim().toLowerCase()];
    if (exact) return exact;
    if (scope === "files" && detail.toLowerCase().startsWith("unsupported image type:")) return "fileUnsupportedType";
    if (scope === "files" && detail.toLowerCase().startsWith("declared content type does not match")) return "fileInvalid";
  }
  if (asObject(detail)?.errors) return scope === "export" ? "exportDocumentInvalid" : "validationDocument";
  if (status === 422) return validationMessageKey(error, scope);
  return null;
}

function defaultDescriptionKey(status: number | null, scope: ApiErrorScope): ErrorKey {
  if (status === 413 && scope === "files") return "uploadTooLarge";
  if (status === 429 && scope === "auth") return "authRateLimited";
  if (status === 429 && scope === "mfa") return "mfaRateLimited";
  if (status === 429 && scope === "files") return "uploadRateLimited";
  if (status === 429 && scope === "export") return "exportRateLimited";
  if (status !== null && status >= 500 && scope === "files") return "fileStorageUnavailable";
  if (status !== null && status >= 500 && scope === "export") return "exportUnavailable";
  switch (status) {
    case 413: return "fileTooLargeDescription";
    case 401: return "sessionExpiredDescription";
    case 403: return "forbiddenDescription";
    case 404: return "notFoundDescription";
    case 409: return "conflictDescription";
    case 422: return validationMessageKey(null, scope);
    case 429: return "rateLimitedDescription";
    default: return status !== null && status >= 500 ? "serverDescription" : "unknownDescription";
  }
}

function kindFromStatus(status: number | null, error: unknown): ApiErrorKind {
  if (isNetworkError(error)) return "network";
  switch (status) {
    case 400: return "bad-request";
    case 401: return "unauthorized";
    case 403: return "forbidden";
    case 404: return "not-found";
    case 409: return "conflict";
    case 413: return "payload-too-large";
    case 422: return "validation";
    case 429: return "rate-limited";
    default: return status !== null && status >= 500 ? "server" : "unknown";
  }
}

function titleKey(kind: ApiErrorKind): ErrorKey {
  switch (kind) {
    case "payload-too-large": return "fileTooLarge";
    case "unauthorized": return "sessionExpired";
    case "forbidden": return "forbidden";
    case "not-found": return "notFound";
    case "conflict": return "conflict";
    case "rate-limited": return "rateLimited";
    case "server": return "server";
    case "network": return "network";
    case "validation": return "validation";
    case "bad-request": return "invalidRequest";
    default: return "unknown";
  }
}

export function apiErrorScopeFromUrl(url: string): ApiErrorScope {
  if (url.includes("/auth/mfa")) return "mfa";
  if (url.includes("/auth/")) return "auth";
  if (url.includes("/files")) return "files";
  if (url.includes("/export") || url.includes("/exports")) return "export";
  if (url.includes("/comments")) return "comments";
  if (url.includes("/internships")) return "internships";
  if (url.includes("/groups")) return "groups";
  if (url.includes("/management")) return "management";
  if (url.includes("/reports")) return "reports";
  if (url.includes("/document-checks") || url.includes("/check-profiles")) return "document";
  return "unknown";
}

export function getApiErrorPresentation(error: unknown, scope: ApiErrorScope = apiErrorScopeFromUrl(requestUrlFrom(error))): ApiErrorPresentation {
  const status = statusFrom(error);
  const kind = kindFromStatus(status, error);
  if (kind === "network") {
    return { kind, status: null, title: i18n.t("errors:network"), description: i18n.t("errors:networkDescription") };
  }
  const descriptionKey = detailMessageKey(error, scope, status) ?? defaultDescriptionKey(status, scope);
  const errorText = i18n.getFixedT(null, "errors");
  return {
    kind,
    status,
    title: errorText(titleKey(kind)),
    description: errorText(descriptionKey),
  };
}

/**
 * Authorization, missing-resource and conflict responses are deterministic;
 * retrying them automatically only creates duplicate requests. Transient
 * failures get one bounded retry, while the UI always keeps a manual retry.
 */
export function shouldRetryQuery(failureCount: number, error: unknown): boolean {
  const { status } = getApiErrorPresentation(error);
  return failureCount < 1 && ![400, 401, 403, 404, 409, 413, 422].includes(status ?? -1);
}
