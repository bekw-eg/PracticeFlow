import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../../lib/api";
import { login, logout } from "./api";

vi.mock("../../lib/api", () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

describe("auth API", () => {
  beforeEach(() => vi.clearAllMocks());

  it("returns the access-token response supplied by login", async () => {
    vi.mocked(api.post).mockResolvedValue({ data: { access_token: "memory-only", token_type: "bearer" } });

    const response = await login({ email: "user@example.com", password: "password", organization_slug: "example" });

    expect(response).toEqual({ access_token: "memory-only", token_type: "bearer" });
    expect(api.post).toHaveBeenCalledWith("/auth/login", {
      email: "user@example.com",
      password: "password",
      organization_slug: "example",
    });
  });

  it("keeps a password-stage MFA challenge distinct from a token", async () => {
    vi.mocked(api.post).mockResolvedValue({ data: { status: "MFA_REQUIRED", challenge_id: "challenge", expires_at: "2026-08-28T12:00:00Z" } });

    await expect(login({ email: "admin@example.com", password: "password", organization_slug: "example" })).resolves.toMatchObject({
      status: "MFA_REQUIRED",
      challenge_id: "challenge",
    });
  });

  it("logs out without sending a JavaScript-readable refresh token", async () => {
    vi.mocked(api.post).mockResolvedValue({ data: undefined });

    await logout();

    expect(api.post).toHaveBeenCalledWith("/auth/logout");
  });
});
