import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "../../lib/api";
import { AuditLogPage } from "./AuditLogPage";

vi.mock("../../lib/api", () => ({ api: { get: vi.fn() } }));

const get = vi.mocked(api.get);
const event = {
  id: "12345678-1234-1234-1234-123456789012",
  timestamp: "2026-08-28T10:00:00Z",
  action: "REPORT_SUBMITTED",
  actor_user_id: "22345678-1234-1234-1234-123456789012",
  target_type: "report",
  target_id: "32345678-1234-1234-1234-123456789012",
  metadata: { version_number: 2 },
  request_id_hash: "a".repeat(64),
  correlation_id_hash: null,
  sequence: 8,
  event_hash: "b".repeat(64),
};

function page(data: unknown[] = [event], total = data.length, offset = 0) {
  return { data, headers: { "x-total-count": String(total), "x-offset": String(offset), "x-limit": "25", "x-has-more": String(offset + data.length < total) } } as never;
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}><AuditLogPage /></QueryClientProvider>);
}

afterEach(() => vi.restoreAllMocks());

describe("AuditLogPage", () => {
  it("filters a server-side page and exposes only safe details", async () => {
    get.mockResolvedValue(page());
    renderPage();

    expect((await screen.findAllByText("Отчёт отправлен")).length).toBeGreaterThan(1);
    expect(screen.getByText(/version_number: 2/)).toBeInTheDocument();
    fireEvent.change(screen.getByRole("combobox", { name: "Действие аудита" }), { target: { value: "REPORT_SUBMITTED" } });
    await waitFor(() => expect(get).toHaveBeenLastCalledWith(expect.stringContaining("action=REPORT_SUBMITTED")));
  });

  it("shows empty and integrity states", async () => {
    get.mockResolvedValueOnce(page([]));
    get.mockResolvedValueOnce({ data: { valid: true, checked_events: 4, first_invalid_sequence: null, retention_anchor_sequence: 0 } } as never);
    renderPage();

    expect(await screen.findByText("Событий по выбранным фильтрам нет")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Проверить целостность" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Цепочка проверена: 4 события.");
  });
});
