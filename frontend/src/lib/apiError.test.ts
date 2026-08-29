import { describe, expect, it } from "vitest";
import { getApiErrorPresentation, shouldRetryQuery } from "./apiError";

describe("API error presentation", () => {
  it.each([
    [413, "Файл слишком большой"],
    [403, "Доступ запрещён"],
    [404, "Данные не найдены"],
    [409, "Обнаружен конфликт данных"],
    [429, "Слишком много запросов"],
    [500, "Ошибка сервера"],
  ])("maps HTTP %i to a user-facing error", (status, title) => {
    expect(getApiErrorPresentation({ response: { status } })).toMatchObject({ status, title });
  });

  it("maps a transport failure to the network-error state", () => {
    expect(getApiErrorPresentation({ code: "ERR_NETWORK", request: {} })).toMatchObject({
      kind: "network",
      title: "Нет соединения с сервером",
      status: null,
    });
  });

  it("does not automatically retry deterministic authorization, missing-resource or conflict responses", () => {
    for (const status of [401, 403, 404, 409]) {
      expect(shouldRetryQuery(0, { response: { status } })).toBe(false);
    }
  });

  it("retries a transient error once and then stops", () => {
    expect(shouldRetryQuery(0, { response: { status: 429 } })).toBe(true);
    expect(shouldRetryQuery(0, { response: { status: 503 } })).toBe(true);
    expect(shouldRetryQuery(0, { code: "ERR_NETWORK", request: {} })).toBe(true);
    expect(shouldRetryQuery(1, { response: { status: 503 } })).toBe(false);
  });
});
