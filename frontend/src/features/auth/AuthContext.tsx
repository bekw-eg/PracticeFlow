import { useEffect, useState, type ReactNode } from "react";
import { fetchCurrentUser, isMfaChallenge, login as loginRequest, logout as logoutRequest, switchOrganization as switchOrganizationRequest, type LoginPayload, type TokenResponse } from "./api";
import { tokenStorage } from "../../lib/tokenStorage";
import { restoreAccessToken } from "../../lib/api";
import type { CurrentUser } from "../../types/api";
import { AuthContext } from "./authContextValue";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const bootstrap = async () => {
      try {
        await restoreAccessToken();
        const me = await fetchCurrentUser();
        setUser(me);
      } catch {
        tokenStorage.clear();
      }
      setIsLoading(false);
    };
    void bootstrap();
  }, []);

  const login = async (payload: LoginPayload) => {
    const result = await loginRequest(payload);
    if (isMfaChallenge(result)) return result;
    await completeMfaSession(result);
    return null;
  };

  const completeMfaSession = async (tokens: TokenResponse) => {
    tokenStorage.setAccessToken(tokens.access_token);
    const me = await fetchCurrentUser();
    setUser(me);
  };

  const logout = async () => {
    try {
      await logoutRequest();
    } catch {
      // Best-effort server-side revocation; clear local state regardless.
    }
    tokenStorage.clear();
    setUser(null);
  };

  const switchOrganization = async (organizationId: string) => {
    const result = await switchOrganizationRequest(organizationId);
    if (isMfaChallenge(result)) return result;
    await completeMfaSession(result);
    return null;
  };

  return <AuthContext.Provider value={{ user, isLoading, login, completeMfaSession, logout, switchOrganization }}>{children}</AuthContext.Provider>;
}
