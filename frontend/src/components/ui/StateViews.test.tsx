import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ErrorState, LoadingState } from "./StateViews";

describe("shared query state views", () => {
  it("exposes loading through an accessible status role", () => {
    render(<LoadingState label="Загрузка профиля…" />);

    expect(screen.getByRole("status")).toHaveTextContent("Загрузка профиля…");
  });

  it("renders an accessible, retryable API error instead of a permanent loader", () => {
    const retry = vi.fn();
    render(<ErrorState error={{ response: { status: 429 } }} onRetry={retry} />);

    expect(screen.getByRole("alert")).toHaveTextContent("Слишком много запросов");
    fireEvent.click(screen.getByRole("button", { name: "Повторить" }));
    expect(retry).toHaveBeenCalledOnce();
  });
});
