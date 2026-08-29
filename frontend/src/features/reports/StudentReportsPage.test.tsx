import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../../lib/api";
import { StudentReportsPage } from "./StudentReportsPage";

const report = {
  id: "12345678-1234-1234-1234-123456789012",
  internship_id: "22345678-1234-1234-1234-123456789012",
  student_id: "32345678-1234-1234-1234-123456789012",
  status: "DRAFT",
  current_version_id: null,
  created_at: "2026-01-01T00:00:00Z",
};

function response(data: unknown[], total: number, offset = 0) {
  return { data, headers: { "x-total-count": String(total), "x-offset": String(offset), "x-limit": "25", "x-has-more": String(offset + data.length < total) } } as never;
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}><MemoryRouter><StudentReportsPage /></MemoryRouter></QueryClientProvider>);
}

afterEach(() => vi.restoreAllMocks());

describe("StudentReportsPage pagination", () => {
  it("moves to the next server page", async () => {
    const get = vi.spyOn(api, "get").mockImplementation((url) => Promise.resolve(String(url).includes("offset=25") ? response([{ ...report, id: "42345678-1234-1234-1234-123456789012" }], 26, 25) : response([report], 26)));
    renderPage();

    await screen.findByText("#12345678");
    fireEvent.click(screen.getByRole("button", { name: "Следующая страница" }));

    await screen.findByText("#42345678");
    expect(get).toHaveBeenCalledWith(expect.stringContaining("offset=25"));
  });

  it("shows a distinct empty result", async () => {
    vi.spyOn(api, "get").mockResolvedValue(response([], 0));
    renderPage();

    expect(await screen.findByText("Отчётов пока нет")).toBeInTheDocument();
  });

  it("retries a failed page request", async () => {
    const get = vi.spyOn(api, "get").mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce(response([], 0));
    renderPage();

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Повторить" }));
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
    expect(await screen.findByText("Отчётов пока нет")).toBeInTheDocument();
  });
});
