import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PaginationControls } from "./PaginationControls";

describe("PaginationControls", () => {
  it("announces the current range and switches pages through labelled controls", () => {
    const onPageChange = vi.fn();
    render(<PaginationControls pagination={{ offset: 25, limit: 25, total: 60, hasMore: true }} onPageChange={onPageChange} label="Отчёты" />);

    expect(screen.getByText("Отчёты: 26–50 из 60")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Предыдущая страница" }));
    fireEvent.click(screen.getByRole("button", { name: "Следующая страница" }));
    expect(onPageChange).toHaveBeenNthCalledWith(1, 0);
    expect(onPageChange).toHaveBeenNthCalledWith(2, 50);
  });
});
