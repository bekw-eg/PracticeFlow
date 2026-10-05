import { afterEach, describe, expect, it } from "vitest";

import { changeLocale, i18n, type Locale } from "../i18n";
import { notificationBody, notificationTitle } from "./notificationContent";

const translate = (locale: Locale) => (key: string) => i18n.t(`common:${key}` as never, { lng: locale });

describe("notification localization", () => {
  afterEach(async () => {
    await changeLocale("ru");
  });

  it.each([
    ["ru", "Требуется доработка отчёта"],
    ["kk", "Есепті толықтыру қажет"],
    ["en", "Report revision requested"],
  ] as const satisfies readonly [Locale, string][])("renders a system title from notification type in %s", async (locale, expected) => {
    await changeLocale(locale);
    expect(notificationTitle({ type: "REVISION_REQUIRED" }, translate(locale))).toBe(expected);
  });

  it.each([
    ["REPORT_DEADLINE_SOON", "ru", "Скоро срок сдачи отчёта"],
    ["REPORT_DEADLINE_SOON", "kk", "Есепті тапсыру мерзімі жақындап қалды"],
    ["REPORT_DEADLINE_SOON", "en", "Report deadline is approaching"],
    ["REPORT_DEADLINE_TODAY", "ru", "Срок сдачи отчёта — сегодня"],
    ["REPORT_DEADLINE_TODAY", "kk", "Есепті тапсыру мерзімі — бүгін"],
    ["REPORT_DEADLINE_TODAY", "en", "Report deadline is today"],
    ["REPORT_DEADLINE_OVERDUE", "ru", "Срок сдачи отчёта истёк"],
    ["REPORT_DEADLINE_OVERDUE", "kk", "Есепті тапсыру мерзімі өтіп кетті"],
    ["REPORT_DEADLINE_OVERDUE", "en", "Report deadline has passed"],
  ] as const satisfies readonly [string, Locale, string][])("localizes %s in %s", async (type, locale, expected) => {
    await changeLocale(locale);
    expect(notificationTitle({ type }, translate(locale))).toBe(expected);
  });

  it("does not translate user-authored notification bodies", () => {
    const authorComment = "Please add the missing weekly summary.";
    expect(notificationBody({ body: authorComment }, translate("kk"))).toBe(authorComment);
    expect(notificationBody({ body: "ИС-101" }, translate("en"))).toBe("ИС-101");
  });

  it("localizes only recognized generated bodies and never reads the stored title", () => {
    expect(notificationBody({ body: "Студент отправил отчёт по практике." }, translate("en"))).toBe("A student submitted an internship report.");
    expect(notificationTitle({ type: "UNKNOWN_TYPE" }, translate("en"))).toBe("New notification");
  });
});
