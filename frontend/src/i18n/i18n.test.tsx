import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { LanguageSwitcher } from "../components/LanguageSwitcher";
import { changeLocale, i18n, restoreLocale } from "./index";
import { LOCALE_STORAGE_KEY } from "./types";

describe("i18n", () => {
  beforeEach(async () => {
    localStorage.clear();
    await changeLocale("ru");
  });

  afterEach(async () => {
    localStorage.clear();
    await changeLocale("ru");
  });

  it("switches the interface language and updates the document language", async () => {
    render(<LanguageSwitcher />);

    fireEvent.change(screen.getByRole("combobox", { name: "Выбор языка" }), { target: { value: "en" } });

    await waitFor(() => expect(i18n.resolvedLanguage).toBe("en"));
    expect(document.documentElement.lang).toBe("en");
    expect(screen.getByRole("combobox", { name: "Language selector" })).toHaveValue("en");
  });

  it("persists the selected language and restores it after a reload or login", async () => {
    await changeLocale("kk");
    expect(localStorage.getItem(LOCALE_STORAGE_KEY)).toBe("kk");

    localStorage.setItem(LOCALE_STORAGE_KEY, "en");
    await restoreLocale();

    expect(i18n.resolvedLanguage).toBe("en");
    expect(document.documentElement.lang).toBe("en");
  });

  it("falls back to Russian and renders a visible marker for an unknown key", async () => {
    const englishSignIn = i18n.getResource("en", "auth", "signIn");
    i18n.addResource("en", "auth", "signIn", "");
    await changeLocale("en");

    expect(i18n.t("auth:signIn")).toBe("Войти");
    expect(i18n.t("common:missingTranslation")).toContain("missingTranslation");

    i18n.addResource("en", "auth", "signIn", englishSignIn);
  });
});
