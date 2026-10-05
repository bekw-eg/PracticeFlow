import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "../../lib/api";
import { LoginPage } from "./LoginPage";

vi.mock("./useAuth", () => ({ useAuth: () => ({ login: vi.fn() }) }));

function renderPage() {
  return render(<MemoryRouter><LoginPage /></MemoryRouter>);
}

function openRecoveryDialog() {
  fireEvent.click(screen.getByRole("button", { name: /Не можете войти/ }));
  return screen.findByRole("dialog");
}

function submitRecoveryRequest(dialog: HTMLElement, email: string) {
  fireEvent.change(within(dialog).getByLabelText("Email"), { target: { value: email } });
  fireEvent.click(within(dialog).getByRole("button", { name: "Отправить инструкции" }));
}

afterEach(() => vi.restoreAllMocks());

describe("LoginPage access recovery", () => {
  it("submits a password-reset request and shows a generic confirmation", async () => {
    const post = vi.spyOn(api, "post").mockResolvedValue({} as never);
    renderPage();

    const dialog = await openRecoveryDialog();
    submitRecoveryRequest(dialog, "student@example.edu");

    expect(await screen.findByRole("status")).toHaveTextContent("Если для указанных данных доступно восстановление");
    expect(post).toHaveBeenCalledWith("/auth/password-reset/request", {
      email: "student@example.edu",
      organization_slug: "demo-university",
    });
  });

  it("uses the same confirmation for an unknown user", async () => {
    vi.spyOn(api, "post").mockResolvedValue({} as never);
    renderPage();

    const dialog = await openRecoveryDialog();
    submitRecoveryRequest(dialog, "unknown@example.edu");

    expect(await screen.findByRole("status")).toHaveTextContent("Если для указанных данных доступно восстановление");
    expect(screen.queryByText(/не найден/i)).not.toBeInTheDocument();
  });

  it("shows a safe rate-limit error without changing the confirmation", async () => {
    vi.spyOn(api, "post").mockRejectedValue({ response: { status: 429, data: { detail: "Too many login attempts." } } });
    renderPage();

    const dialog = await openRecoveryDialog();
    submitRecoveryRequest(dialog, "student@example.edu");

    expect(await screen.findByRole("alert")).toHaveTextContent("Слишком много запросов на восстановление");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});
