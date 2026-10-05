import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { changeLocale } from "../i18n";
import { ToastViewport } from "./ToastViewport";

describe("ToastViewport", () => {
  afterEach(async () => {
    await changeLocale("ru");
  });

  it("announces added toasts through a localized live region", async () => {
    await changeLocale("en");
    render(<ToastViewport />);

    act(() => window.dispatchEvent(new CustomEvent("pf:toast", { detail: { message: "Saved", tone: "success" } })));

    expect(screen.getByRole("region", { name: "Application notifications" })).toHaveAttribute("aria-live", "polite");
    expect(screen.getByRole("status")).toHaveTextContent("Saved");
    expect(screen.getByRole("button", { name: "Close notification" })).toBeInTheDocument();
  });
});
