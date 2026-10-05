import { en } from "./locales/en";
import { kk } from "./locales/kk";
import { ru } from "./locales/ru";
import { disciplinesRu, disciplinesEn, disciplinesKk } from "./locales/disciplines";

export const resources = {
  ru: { ...ru, disciplines: disciplinesRu },
  kk: { ...kk, disciplines: disciplinesKk },
  en: { ...en, disciplines: disciplinesEn },
} as const;

export type TranslationResources = typeof resources.ru;
