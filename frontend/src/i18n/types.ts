export const supportedLocales = ["ru", "kk", "en"] as const;

export type Locale = (typeof supportedLocales)[number];

export const DEFAULT_LOCALE: Locale = "ru";
export const LOCALE_STORAGE_KEY = "practiceflow.locale";

export const namespaces = ["common", "auth", "groups", "templates", "reports", "editor", "documentChecks", "admin", "audit", "export", "errors", "disciplines"] as const;

export type TranslationNamespace = (typeof namespaces)[number];

export function isLocale(value: string | null | undefined): value is Locale {
  return typeof value === "string" && (supportedLocales as readonly string[]).includes(value);
}

type Join<Key, Prefix> = Key extends string ? Prefix extends string ? `${Prefix}.${Key}` : never : never;

export type NestedTranslationKey<Value> = Value extends string
  ? never
  : {
      [Key in keyof Value & string]: Value[Key] extends string
        ? Key
        : Join<Key, NestedTranslationKey<Value[Key]>>;
    }[keyof Value & string];

export type TranslationKey<Resources, Namespace extends keyof Resources> = NestedTranslationKey<Resources[Namespace]>;

export type TranslationShape<Value> = {
  [Key in keyof Value]: Value[Key] extends string ? string : TranslationShape<Value[Key]>;
};
