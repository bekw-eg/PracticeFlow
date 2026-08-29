import { beforeEach, describe, expect, it } from "vitest";

import { tokenStorage } from "./tokenStorage";

describe("tokenStorage", () => {
  beforeEach(() => {
    tokenStorage.clear();
    localStorage.clear();
  });

  it("keeps the access token only in module memory", () => {
    tokenStorage.setAccessToken("access-value");

    expect(tokenStorage.getAccessToken()).toBe("access-value");
    expect(localStorage.length).toBe(0);

    tokenStorage.clear();
    expect(tokenStorage.getAccessToken()).toBeNull();
  });
});
