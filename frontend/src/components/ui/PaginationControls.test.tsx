import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { changeLocale } from "../../i18n";
import { PaginationControls } from "./PaginationControls";

describe("PaginationControls", () => {
  afterEach(async () => {
    await changeLocale("ru");
  });

  it.each([
    { locale: "ru" as const, label: "Отчёты", range: "Отчёты: 26–50 из 60", previous: "Предыдущая страница", next: "Следующая страница" },
    { locale: "kk" as const, label: "Есептер", range: "Есептер: 26–50 / 60", previous: "Алдыңғы бет", next: "Келесі бет" },
    { locale: "en" as const, label: "Reports", range: "Reports: 26–50 of 60", previous: "Previous page", next: "Next page" },
  ])("announces the current range and labels controls in $locale", async ({ locale, label, range, previous, next }) => {
    await changeLocale(locale);
    const onPageChange = vi.fn();
    render(<PaginationControls pagination={{ offset: 25, limit: 25, total: 60, hasMore: true }} onPageChange={onPageChange} label={label} />);

    expect(screen.getByText(range)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: previous }));
    fireEvent.click(screen.getByRole("button", { name: next }));
    expect(onPageChange).toHaveBeenNthCalledWith(1, 0);
    expect(onPageChange).toHaveBeenNthCalledWith(2, 50);
  });
});
