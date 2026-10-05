import i18n from "i18next";
import ICU from "i18next-icu";
import { initReactI18next } from "react-i18next";
import { DEFAULT_LOCALE, isLocale, LOCALE_STORAGE_KEY, namespaces, type Locale } from "./types";
import { resources } from "./resources";

function browserStorage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

export function storedLocale(): Locale {
  const locale = browserStorage()?.getItem(LOCALE_STORAGE_KEY);
  return isLocale(locale) ? locale : DEFAULT_LOCALE;
}

function updateDocumentLanguage(locale: Locale) {
  if (typeof document !== "undefined") document.documentElement.lang = locale;
}

void i18n
  .use(ICU)
  .use(initReactI18next)
  .init({
    resources,
    lng: storedLocale(),
    fallbackLng: DEFAULT_LOCALE,
    supportedLngs: ["ru", "kk", "en"],
    ns: namespaces,
    defaultNS: "common",
    interpolation: { escapeValue: false },
    returnNull: false,
    returnEmptyString: false,
    saveMissing: false,
    parseMissingKeyHandler: (key) => `[${key}]`,
    react: { useSuspense: false },
  });

i18n.on("languageChanged", (language) => {
  const locale = isLocale(language) ? language : DEFAULT_LOCALE;
  browserStorage()?.setItem(LOCALE_STORAGE_KEY, locale);
  updateDocumentLanguage(locale);
});

updateDocumentLanguage(storedLocale());

export async function changeLocale(locale: Locale) {
  await i18n.changeLanguage(locale);
}

export async function restoreLocale() {
  await changeLocale(storedLocale());
}

export { i18n };
export type { Locale, TranslationNamespace } from "./types";
