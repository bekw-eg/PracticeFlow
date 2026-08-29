import axios, { type AxiosInstance, type InternalAxiosRequestConfig } from "axios";
import { tokenStorage } from "./tokenStorage";
import { showToast } from "./toast";
import { getApiErrorPresentation } from "./apiError";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

export const api: AxiosInstance = axios.create({ baseURL: API_BASE_URL, withCredentials: true });

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = tokenStorage.getAccessToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

let refreshPromise: Promise<string> | null = null;

async function refreshAccessToken(): Promise<string> {
  // Deliberately a bare axios call (not `api`) to avoid recursing through
  // the response interceptor below while a refresh is already in flight.
  const response = await axios.post(`${API_BASE_URL}/auth/refresh`, undefined, { withCredentials: true });
  const { access_token } = response.data;
  tokenStorage.setAccessToken(access_token);
  return access_token;
}

export async function restoreAccessToken(): Promise<string> {
  return refreshAccessToken();
}

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    const url = String(originalRequest?.url ?? "");
    const isSessionEndpoint = url.includes("/auth/login") || url.includes("/auth/refresh") || url.includes("/auth/logout") || url.includes("/auth/mfa");
    if (error.response?.status === 401 && !originalRequest._retry && !isSessionEndpoint) {
      originalRequest._retry = true;
      try {
        // Coalesce concurrent 401s into a single refresh call.
        refreshPromise ??= refreshAccessToken().finally(() => {
          refreshPromise = null;
        });
        const newAccessToken = await refreshPromise;
        originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
        return api(originalRequest);
      } catch {
        tokenStorage.clear();
        if (window.location.pathname !== "/login") window.location.href = "/login";
      }
    }
    const isReadRequest = originalRequest?.method?.toLowerCase() === "get";
    const isStaleDocumentConflict = error.response?.status === 409 && error.response.data?.detail?.code === "STALE_DOCUMENT_REVISION";
    if (error.response?.status && error.response.status !== 401 && !isReadRequest && !isStaleDocumentConflict) {
      showToast(getApiErrorPresentation(error).description, "error");
    }
    return Promise.reject(error);
  }
);
