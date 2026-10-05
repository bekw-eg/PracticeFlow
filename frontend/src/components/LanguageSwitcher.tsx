import { useTranslation } from "react-i18next";
import { changeLocale, type Locale } from "../i18n";
import { supportedLocales } from "../i18n/types";

type LanguageSwitcherProps = {
  className?: string;
};

export function LanguageSwitcher({ className = "" }: LanguageSwitcherProps) {
  const { i18n, t } = useTranslation("common");
  const currentLocale = supportedLocales.includes(i18n.resolvedLanguage as Locale)
    ? i18n.resolvedLanguage as Locale
    : "ru";

  return (
    <label className={`inline-flex items-center gap-2 text-sm font-medium text-[var(--color-ink-soft)] ${className}`}>
      <span className="sr-only">{t("language")}</span>
      <select
        aria-label={t("languageSelector")}
        className="rounded-lg border border-[var(--color-border)] bg-white px-2 py-1.5 text-sm text-[var(--color-ink)] outline-none transition focus:border-[var(--color-brand-500)]"
        value={currentLocale}
        onChange={(event) => void changeLocale(event.target.value as Locale)}
      >
        {supportedLocales.map((locale) => <option key={locale} value={locale}>{t(`languages.${locale}`)}</option>)}
      </select>
    </label>
  );
}
