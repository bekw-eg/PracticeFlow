import { createContext } from "react";

import type { CurrentUser } from "../../types/api";
import type { LoginPayload, MfaChallenge, TokenResponse } from "./api";

export interface AuthContextValue {
  user: CurrentUser | null;
  isLoading: boolean;
  login: (payload: LoginPayload) => Promise<MfaChallenge | null>;
  completeMfaSession: (tokens: TokenResponse) => Promise<void>;
  logout: () => Promise<void>;
  switchOrganization: (organizationId: string) => Promise<MfaChallenge | null>;
}

export const AuthContext = createContext<AuthContextValue | undefined>(undefined);
