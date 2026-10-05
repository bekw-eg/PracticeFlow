import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import { changeLocale } from "../../i18n";
import { CompleteAccessPage } from "./CompleteAccessPage";

describe("CompleteAccessPage localization", () => {
  afterEach(async () => {
    await changeLocale("ru");
  });

  it.each([
    ["ru", "Установите пароль", "Новый пароль"],
    ["kk", "Құпиясөз орнатыңыз", "Жаңа құпиясөз"],
    ["en", "Set a password", "New password"],
  ] as const)("uses %s UI strings", async (locale, heading, passwordLabel) => {
    await changeLocale(locale);
    render(<MemoryRouter initialEntries={["/access?token=test-token"]}><CompleteAccessPage /></MemoryRouter>);

    expect(screen.getByRole("heading", { name: heading })).toBeInTheDocument();
    expect(screen.getByText(passwordLabel)).toBeInTheDocument();
  });
});
