import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MfaPage } from "./MfaPage";
import { startMfaEnrollment, submitMfaRecoveryCode } from "./api";
import { changeLocale } from "../../i18n";

const completeMfaSession = vi.fn();

vi.mock("./useAuth", () => ({ useAuth: () => ({ completeMfaSession }) }));
vi.mock("./api", () => ({
  startMfaEnrollment: vi.fn(),
  submitMfaRecoveryCode: vi.fn(),
  verifyMfaCode: vi.fn(),
  verifyMfaEnrollment: vi.fn(),
  requestPeerMfaRecovery: vi.fn(),
  getPeerMfaRecoveryStatus: vi.fn(),
  completePeerMfaRecovery: vi.fn(),
}));

const challenge = { status: "MFA_REQUIRED" as const, challenge_id: "challenge-1", expires_at: "2026-08-28T12:00:00Z" };

describe("MfaPage recovery", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    vi.mocked(startMfaEnrollment).mockResolvedValue({ challenge_id: "challenge-2", expires_at: "2026-08-28T12:00:00Z", manual_key: "ABCDEFGHIJKLMNOP", qr_data_url: "data:image/png;base64,abc" });
  });

  it.each([
    ["ru", "Подтвердите вход"],
    ["kk", "Кіруді растаңыз"],
    ["en", "Confirm sign in"],
  ] as const)("renders the MFA screen in %s", async (locale, title) => {
    await changeLocale(locale);
    render(<MemoryRouter initialEntries={[{ pathname: "/mfa", state: { challenge } }]}><MfaPage /></MemoryRouter>);
    expect(await screen.findByRole("heading", { name: title })).toBeInTheDocument();
  });

  it("moves recovery-code users into fresh enrollment rather than a session", async () => {
    await changeLocale("ru");
    vi.mocked(submitMfaRecoveryCode).mockResolvedValue({ status: "MFA_ENROLLMENT_REQUIRED", challenge_id: "challenge-2", expires_at: "2026-08-28T12:00:00Z" });
    render(<MemoryRouter initialEntries={[{ pathname: "/mfa", state: { challenge } }]}><MfaPage /></MemoryRouter>);

    fireEvent.click(await screen.findByRole("button", { name: "Использовать recovery code" }));
    fireEvent.change(screen.getByLabelText("Одноразовый recovery code"), { target: { value: "ABCD-EFGH-IJKL" } });
    fireEvent.click(screen.getByRole("button", { name: "Продолжить с recovery code" }));

    await waitFor(() => expect(startMfaEnrollment).toHaveBeenCalledWith("challenge-2"));
    expect(await screen.findByText("Если камера недоступна, введите ключ вручную:")).toBeInTheDocument();
    expect(completeMfaSession).not.toHaveBeenCalled();
  });
});
