import { en } from "./locales/en";
import { kk } from "./locales/kk";
import { ru } from "./locales/ru";

export const resources = {
  ru: { ...ru },
  kk: { ...kk },
  en: { ...en },
} as const;

export type TranslationResources = typeof ru;
