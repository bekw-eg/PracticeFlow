import { renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { AuthContext, type AuthContextValue } from "./authContextValue";
import { useProductFeatures } from "./useProductFeatures";


describe("useProductFeatures", () => {
  it("keeps document checks enabled by default outside the auth provider", () => {
    const { result } = renderHook(() => useProductFeatures());

    expect(result.current).toEqual({
      document_check_enabled: true,
    });
  });

  it("uses the feature flags returned by the current-user API", () => {
    const value: AuthContextValue = {
      user: {
        user_id: "user-1",
        organization_id: "organization-1",
        full_name: "Teacher",
        email: "teacher@example.edu",
        role: "TEACHER",
        features: {
          document_check_enabled: false,
        },
      },
      isLoading: false,
      login: vi.fn(async () => null),
      completeMfaSession: vi.fn(async () => undefined),
      logout: vi.fn(async () => undefined),
      switchOrganization: vi.fn(async () => null),
    };
    const wrapper = ({ children }: { children: ReactNode }) => (
      <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
    );

    const { result } = renderHook(() => useProductFeatures(), { wrapper });

    expect(result.current.document_check_enabled).toBe(false);
  });
});
