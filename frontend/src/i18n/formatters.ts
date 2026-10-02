import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import { DEFAULT_LOCALE, isLocale, type Locale } from "./types";

export type AppDate = Date | string | number;
export type PluralCategory = Intl.LDMLPluralRule;

const intlLocales: Record<Locale, string> = {
  ru: "ru-RU",
  kk: "kk-KZ",
  en: "en-US",
};

function asDate(value: AppDate) {
  return value instanceof Date ? value : new Date(value);
}

export function localeForIntl(language: string | null | undefined): string {
  return intlLocales[isLocale(language) ? language : DEFAULT_LOCALE];
}

export function formatDate(value: AppDate, locale: string, options: Intl.DateTimeFormatOptions = {}) {
  return new Intl.DateTimeFormat(localeForIntl(locale), { dateStyle: "medium", ...options }).format(asDate(value));
}

export function formatDateTime(value: AppDate, locale: string, options: Intl.DateTimeFormatOptions = {}) {
  return new Intl.DateTimeFormat(localeForIntl(locale), { dateStyle: "medium", timeStyle: "short", ...options }).format(asDate(value));
}

export function formatNumber(value: number, locale: string, options: Intl.NumberFormatOptions = {}) {
  return new Intl.NumberFormat(localeForIntl(locale), options).format(value);
}

export function formatPercent(value: number, locale: string, options: Intl.NumberFormatOptions = {}) {
  return new Intl.NumberFormat(localeForIntl(locale), { style: "percent", maximumFractionDigits: 0, ...options }).format(value);
}

export function formatFileSize(bytes: number, locale: string) {
  const units = ["byte", "kilobyte", "megabyte", "gigabyte", "terabyte"] as const;
  const safeBytes = Math.max(0, bytes);
  const exponent = safeBytes === 0 ? 0 : Math.min(Math.floor(Math.log(safeBytes) / Math.log(1024)), units.length - 1);
  const value = safeBytes / 1024 ** exponent;
  return new Intl.NumberFormat(localeForIntl(locale), {
    style: "unit",
    unit: units[exponent],
    unitDisplay: "short",
    maximumFractionDigits: value >= 10 || exponent === 0 ? 0 : 1,
  }).format(value);
}

export function pluralCategory(value: number, locale: string): PluralCategory {
  return new Intl.PluralRules(localeForIntl(locale), { type: "cardinal" }).select(value);
}

export type CountMessageValues = {
  count: number;
};

export function formatCount<T>(count: number, message: (values: CountMessageValues) => T): T {
  return message({ count });
}

export function formatNotificationBadge(count: number, locale: string, maximum = 9) {
  return count > maximum ? `${formatNumber(maximum, locale)}+` : formatNumber(count, locale);
}

export function useLocaleFormatters() {
  const { i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? i18n.language;

  return useMemo(() => ({
    locale,
    formatDate: (value: AppDate, options?: Intl.DateTimeFormatOptions) => formatDate(value, locale, options),
    formatDateTime: (value: AppDate, options?: Intl.DateTimeFormatOptions) => formatDateTime(value, locale, options),
    formatNumber: (value: number, options?: Intl.NumberFormatOptions) => formatNumber(value, locale, options),
    formatPercent: (value: number, options?: Intl.NumberFormatOptions) => formatPercent(value, locale, options),
    formatFileSize: (bytes: number) => formatFileSize(bytes, locale),
    formatCount: <T,>(count: number, message: (values: CountMessageValues) => T) => formatCount(count, message),
    formatNotificationBadge: (count: number, maximum?: number) => formatNotificationBadge(count, locale, maximum),
    pluralCategory: (value: number) => pluralCategory(value, locale),
  }), [locale]);
}
