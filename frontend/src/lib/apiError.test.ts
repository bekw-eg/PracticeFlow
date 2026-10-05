import { afterEach, describe, expect, it } from "vitest";

import { changeLocale, type Locale } from "../i18n";
import { getApiErrorPresentation, shouldRetryQuery } from "./apiError";

const backendError = (status: number, detail: unknown) => ({ response: { status, data: { detail } } });

describe("API error presentation", () => {
  afterEach(async () => {
    await changeLocale("ru");
  });

  it.each([
    [401, "Invalid credentials", "unauthorized"],
    [403, "Organization is not available to this user", "forbidden"],
    [404, "Report not found", "not-found"],
    [409, "Report is not currently editable", "conflict"],
    [413, "Image exceeds the configured file-size limit.", "payload-too-large"],
    [422, [{ loc: ["body", "email"], type: "value_error.email" }], "validation"],
    [429, "Too many login attempts. Try again in a few minutes.", "rate-limited"],
    [503, "Internal implementation detail", "server"],
  ] as const)("maps HTTP %i without exposing its backend detail", (status, detail, kind) => {
    const presentation = getApiErrorPresentation(backendError(status, detail), status === 429 ? "auth" : "unknown");

    expect(presentation).toMatchObject({ status, kind });
    expect(presentation.title).not.toContain("detail");
    expect(presentation.description).not.toContain(typeof detail === "string" ? detail : "value_error.email");
  });

  it.each([
    ["ru", "Неверный код подтверждения. Попробуйте ещё раз."],
    ["kk", "Растау коды қате. Қайталап көріңіз."],
    ["en", "The verification code is incorrect. Try again."],
  ] as const satisfies readonly [Locale, string][])("localizes MFA errors in %s", async (locale, expected) => {
    await changeLocale(locale);
    expect(getApiErrorPresentation(backendError(401, "Invalid authentication code"), "mfa").description).toBe(expected);
  });

  it("maps validation field/type and document machine code to safe messages", () => {
    expect(getApiErrorPresentation(backendError(422, [{ loc: ["body", "email"], type: "value_error.email" }]), "auth").description)
      .toBe("Введите корректный адрес электронной почты.");
    expect(getApiErrorPresentation(backendError(409, { code: "STALE_DOCUMENT_REVISION", message: "Document was changed in another tab." }), "document").description)
      .toBe("Документ был изменён в другой вкладке. Обновите данные перед сохранением.");
  });

  it("uses the safe fallback for an unknown backend message", () => {
    const rawDetail = "Sensitive implementation failure: postgres://internal";
    const presentation = getApiErrorPresentation(backendError(400, rawDetail), "management");

    expect(presentation.description).toBe("Попробуйте повторить попытку. Если проблема сохранится, обратитесь к администратору.");
    expect(presentation.description).not.toContain(rawDetail);
  });

  it("maps a transport failure to the network-error state", () => {
    expect(getApiErrorPresentation({ code: "ERR_NETWORK", request: {} })).toMatchObject({
      kind: "network",
      title: "Нет соединения с сервером",
      status: null,
    });
  });

  it("does not automatically retry deterministic responses", () => {
    for (const status of [400, 401, 403, 404, 409, 413, 422]) {
      expect(shouldRetryQuery(0, backendError(status, "raw detail"))).toBe(false);
    }
  });

  it("retries a transient error once and then stops", () => {
    expect(shouldRetryQuery(0, backendError(429, "raw detail"))).toBe(true);
    expect(shouldRetryQuery(0, backendError(503, "raw detail"))).toBe(true);
    expect(shouldRetryQuery(0, { code: "ERR_NETWORK", request: {} })).toBe(true);
    expect(shouldRetryQuery(1, backendError(503, "raw detail"))).toBe(false);
  });
});
