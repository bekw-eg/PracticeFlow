import { afterEach, describe, expect, it } from "vitest";

import { changeLocale, i18n, type Locale } from "../i18n";
import { notificationBody, notificationTitle } from "./notificationContent";

const translate = (locale: Locale) => (key: string) => i18n.t(`common:${key}` as never, { lng: locale });

describe("notification localization", () => {
  afterEach(async () => {
    await changeLocale("ru");
  });

  it.each([
    ["DOCUMENT_CHECK_ASSIGNED", "ru", "Назначена проверка документа"],
    ["DOCUMENT_CHECK_ASSIGNED", "kk", "Құжатты тексеру тағайындалды"],
    ["DOCUMENT_CHECK_ASSIGNED", "en", "Document check assigned"],
  ] as const satisfies readonly [string, Locale, string][])("localizes %s in %s", async (type, locale, expected) => {
    await changeLocale(locale);
    expect(notificationTitle({ type }, translate(locale))).toBe(expected);
  });

  it("does not translate user-authored notification bodies", () => {
    const authorComment = "Please review the latest submission.";
    expect(notificationBody({ body: authorComment })).toBe(authorComment);
    expect(notificationBody({ body: "ИС-101" })).toBe("ИС-101");
    expect(notificationBody({ body: null })).toBeNull();
  });

  it("falls back to generic title for unknown notification types", () => {
    expect(notificationTitle({ type: "UNKNOWN_TYPE" }, translate("en"))).toBe("New notification");
  });
});
