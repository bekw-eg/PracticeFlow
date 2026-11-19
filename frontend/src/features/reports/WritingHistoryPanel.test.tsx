import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "../../lib/api";
import type { WritingHistory } from "../../types/api";
import { WritingHistoryPanel } from "./WritingHistoryPanel";

afterEach(() => vi.restoreAllMocks());

function renderPanel(data: WritingHistory | Error) {
  const get = vi.spyOn(api, "get").mockImplementation(() => (data instanceof Error ? Promise.reject(data) : Promise.resolve({ data } as never)));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(<QueryClientProvider client={client}><WritingHistoryPanel reportId="report-1" /></QueryClientProvider>);
  return { ...view, get };
}

const history: WritingHistory = {
  current_words: 1240, active_days: 3, total_saves: 41, largest_save_words: 820, large_save_threshold: 300,
  days: [
    { date: "2026-11-02", word_count: 300, words_added: 300, saves: 12, largest_save_words: 40 },
    { date: "2026-11-05", word_count: 1150, words_added: 850, saves: 3, largest_save_words: 820 },
    { date: "2026-11-09", word_count: 1240, words_added: 90, saves: 26, largest_save_words: 25 },
  ],
};

describe("WritingHistoryPanel", () => {
  it("shows counts, a bar per day and flags a large single-save addition", async () => {
    const { container, get } = renderPanel(history);

    expect(await screen.findByText("Слов сейчас: 1 240")).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith("/reports/report-1/writing-history");
    expect(screen.getByText("Дней с работой: 3")).toBeInTheDocument();
    expect(screen.getByText("Сохранений: 41")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Рост числа слов по дням" })).toBeInTheDocument();
    expect(container.querySelectorAll("rect")).toHaveLength(3);
    expect(container.querySelectorAll("rect[data-large-save]")).toHaveLength(1);
    expect(screen.getByRole("note")).toHaveTextContent("820 слов");
  });

  it("does not flag steady writing", async () => {
    renderPanel({ ...history, largest_save_words: 120, days: history.days.map((day) => ({ ...day, largest_save_words: 40 })) });
    await screen.findByText("Слов сейчас: 1 240");
    expect(screen.queryByRole("note")).not.toBeInTheDocument();
  });

  it("explains an empty history", async () => {
    renderPanel({ current_words: null, active_days: 0, total_saves: 0, largest_save_words: 0, large_save_threshold: 300, days: [] });
    expect(await screen.findByText("Студент ещё не сохранял черновик.")).toBeInTheDocument();
  });

  it("shows a retryable error", async () => {
    renderPanel(new Error("boom"));
    expect(await screen.findByText("Не удалось загрузить историю написания.")).toBeInTheDocument();
  });
});
