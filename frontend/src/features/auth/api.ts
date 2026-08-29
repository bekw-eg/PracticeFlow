import { api } from "../../lib/api";
import { DEFAULT_PAGE_SIZE, fetchPage } from "../../lib/pagination";
import type { CurrentUser, OrganizationChoice } from "../../types/api";

export interface LoginPayload {
  email: string;
  password: string;
  organization_slug: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface MfaChallenge {
  status: "MFA_REQUIRED" | "MFA_ENROLLMENT_REQUIRED" | "MFA_RECOVERY_PENDING";
  challenge_id: string;
  expires_at: string;
}

export interface MfaEnrollmentStart {
  challenge_id: string;
  expires_at: string;
  manual_key: string;
  qr_data_url: string;
}

export interface MfaEnrollmentComplete extends TokenResponse {
  recovery_codes: string[];
}

export interface MfaPeerRecoveryStatus {
  status: "MFA_RECOVERY_PENDING" | "MFA_ENROLLMENT_REQUIRED";
  challenge_id: string;
  expires_at: string;
  approved: boolean;
}

export type AuthResponse = TokenResponse | MfaChallenge;

export function isMfaChallenge(response: AuthResponse): response is MfaChallenge {
  return "challenge_id" in response;
}

export async function login(payload: LoginPayload): Promise<AuthResponse> {
  const { data } = await api.post<AuthResponse>("/auth/login", payload);
  return data;
}

export async function fetchCurrentUser(): Promise<CurrentUser> {
  const { data } = await api.get<CurrentUser>("/auth/me");
  return data;
}

export async function logout(): Promise<void> {
  await api.post("/auth/logout");
}

export async function fetchOrganizations(): Promise<OrganizationChoice[]> {
  return (await api.get<OrganizationChoice[]>("/auth/organizations")).data;
}

export function fetchOrganizationsPage(offset: number) {
  return fetchPage<OrganizationChoice>("/auth/organizations", { offset, limit: DEFAULT_PAGE_SIZE });
}

export async function switchOrganization(organizationId: string): Promise<AuthResponse> {
  return (await api.post<AuthResponse>("/auth/switch-organization", { organization_id: organizationId })).data;
}

export async function startMfaEnrollment(challengeId: string): Promise<MfaEnrollmentStart> {
  return (await api.post<MfaEnrollmentStart>("/auth/mfa/enrollment/start", { challenge_id: challengeId })).data;
}

export async function verifyMfaEnrollment(challengeId: string, code: string): Promise<MfaEnrollmentComplete> {
  return (await api.post<MfaEnrollmentComplete>("/auth/mfa/enrollment/verify", { challenge_id: challengeId, code })).data;
}

export async function verifyMfaCode(challengeId: string, code: string): Promise<TokenResponse> {
  return (await api.post<TokenResponse>("/auth/mfa/verify", { challenge_id: challengeId, code })).data;
}

export async function submitMfaRecoveryCode(challengeId: string, recoveryCode: string): Promise<MfaChallenge> {
  return (await api.post<MfaChallenge>("/auth/mfa/recovery/verify", { challenge_id: challengeId, recovery_code: recoveryCode })).data;
}

export async function requestPeerMfaRecovery(challengeId: string): Promise<MfaPeerRecoveryStatus> {
  return (await api.post<MfaPeerRecoveryStatus>("/auth/mfa/recovery/peer-request", { challenge_id: challengeId })).data;
}

export async function getPeerMfaRecoveryStatus(challengeId: string): Promise<MfaPeerRecoveryStatus> {
  return (await api.get<MfaPeerRecoveryStatus>(`/auth/mfa/recovery/peer-status/${challengeId}`)).data;
}

export async function completePeerMfaRecovery(challengeId: string): Promise<MfaChallenge> {
  return (await api.post<MfaChallenge>("/auth/mfa/recovery/complete-peer", { challenge_id: challengeId })).data;
}
