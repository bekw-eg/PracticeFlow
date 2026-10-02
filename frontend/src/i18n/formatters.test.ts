import { afterEach, describe, expect, it } from "vitest";

import { changeLocale, i18n, type Locale } from "./index";
import {
  formatCount,
  formatDate,
  formatDateTime,
  formatFileSize,
  formatNotificationBadge,
  formatNumber,
  formatPercent,
  pluralCategory,
} from "./formatters";

const counts = [0, 1, 2, 5, 11, 21, 101] as const;

const pluralCategories: Record<Locale, readonly Intl.LDMLPluralRule[]> = {
  ru: ["many", "one", "few", "many", "many", "one", "one"],
  kk: ["other", "one", "other", "other", "other", "other", "other"],
  en: ["other", "one", "other", "other", "other", "other", "other"],
};

const studentLabels: Record<Locale, readonly string[]> = {
  ru: ["0 студентов", "1 студент", "2 студента", "5 студентов", "11 студентов", "21 студент", "101 студент"],
  kk: ["0 студент", "1 студент", "2 студент", "5 студент", "11 студент", "21 студент", "101 студент"],
  en: ["0 students", "1 student", "2 students", "5 students", "11 students", "21 students", "101 students"],
};

describe("locale formatters", () => {
  afterEach(async () => {
    await changeLocale("ru");
  });

  it.each((Object.keys(pluralCategories) as Locale[]).flatMap((locale) => counts.map((count, index) => ({ locale, count, expected: pluralCategories[locale][index] }))))(
    "uses the $expected cardinal plural category for $count in $locale",
    ({ locale, count, expected }) => {
      expect(pluralCategory(count, locale)).toBe(expected);
    },
  );

  it.each((Object.keys(studentLabels) as Locale[]).flatMap((locale) => counts.map((count, index) => ({ locale, count, expected: studentLabels[locale][index] }))))(
    "formats $count students in $locale",
    async ({ locale, count, expected }) => {
      await changeLocale(locale);
      const text = formatCount(count, (values) => i18n.t("groups:studentCount", values));

      expect(text).toBe(expected);
    },
  );

  it.each(["ru", "kk", "en"] as const)("formats dates, numbers, percentages, file sizes, and badges in %s", (locale) => {
    expect(formatDate("2026-08-31", locale)).toContain("2026");
    expect(formatDateTime("2026-08-31T10:30:00Z", locale)).toContain("2026");
    expect(formatNumber(1_234_567.5, locale)).not.toBe("1234567.5");
    expect(formatPercent(0.125, locale)).toContain("13");
    expect(formatFileSize(1_536, locale)).toBeTruthy();
    expect(formatNotificationBadge(12, locale)).toBe("9+");
  });
});
