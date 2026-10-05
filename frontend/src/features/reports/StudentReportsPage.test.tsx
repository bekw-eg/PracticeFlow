import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../../lib/api";
import * as toast from "../../lib/toast";
import { StudentReportsPage } from "./StudentReportsPage";

const report = {
  id: "12345678-1234-1234-1234-123456789012",
  internship_id: "22345678-1234-1234-1234-123456789012",
  student_id: "32345678-1234-1234-1234-123456789012",
  status: "DRAFT",
  current_version_id: null,
  created_at: "2026-01-01T00:00:00Z",
  internship_title: "Летняя производственная практика",
  internship_description: "Подготовьте дневник практики и приложите отзыв руководителя.",
  group_name: "BK-2405",
  start_date: "2026-06-01",
  end_date: "2026-07-15",
  deadline: "2026-07-20",
  deadline_state: "DUE_SOON",
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
  it("shows the internship context and a localized deadline state", async () => {
    vi.spyOn(api, "get").mockResolvedValue(response([report], 1));
    renderPage();

    expect(await screen.findByText("Летняя производственная практика")).toBeInTheDocument();
    expect(screen.getByText("Группа: BK-2405")).toBeInTheDocument();
    expect(screen.getByText(/Период:/)).toBeInTheDocument();
    expect(screen.getByText(/Дедлайн:/)).toBeInTheDocument();
    expect(screen.getByText("Срок скоро")).toBeInTheDocument();
    expect(screen.getByText("Инструкции от преподавателя")).toBeInTheDocument();
    expect(screen.getByText("Подготовьте дневник практики и приложите отзыв руководителя.")).toBeInTheDocument();
  });

  it("renders every deadline visual state supplied by the read model", async () => {
    const states = [
      ["UPCOMING", "Срок впереди"],
      ["DUE_SOON", "Срок скоро"],
      ["DUE_TODAY", "Срок сегодня"],
      ["OVERDUE", "Срок просрочен"],
      ["SUBMITTED_ON_TIME", "Отправлено вовремя"],
      ["SUBMITTED_LATE", "Отправлено с опозданием"],
    ] as const;
    vi.spyOn(api, "get").mockResolvedValue(response(states.map(([deadline_state], index) => ({
      ...report,
      id: `12345678-1234-1234-1234-1234567890${index}`,
      deadline_state,
    })), states.length));
    renderPage();

    for (const [, label] of states) expect(await screen.findByText(label)).toBeInTheDocument();
  });

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

describe("StudentReportsPage submission", () => {
  it("shows success feedback and refreshes the report list after submission", async () => {
    const submittedReport = { ...report, status: "SUBMITTED" };
    const get = vi.spyOn(api, "get").mockResolvedValueOnce(response([report], 1)).mockResolvedValueOnce(response([submittedReport], 1));
    const post = vi.spyOn(api, "post").mockResolvedValue({ data: submittedReport } as never);
    const showToast = vi.spyOn(toast, "showToast");
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Отправить на проверку" }));

    await waitFor(() => expect(showToast).toHaveBeenCalledWith("Отчёт отправлен на проверку."));
    await screen.findByText("Отправлено");
    expect(post).toHaveBeenCalledWith(`/reports/${report.id}/submit`);
    expect(get).toHaveBeenCalledTimes(2);
  });

  it("shows a validation checklist beside the report when submission returns 422", async () => {
    vi.spyOn(api, "get").mockResolvedValue(response([report], 1));
    vi.spyOn(api, "post").mockRejectedValue({
      response: {
        status: 422,
        data: { detail: { errors: ["Обязательный раздел «Введение» отсутствует.", "Обязательный раздел «Заключение» отсутствует."] } },
      },
    });
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Отправить на проверку" }));

    const error = await screen.findByRole("alert");
    expect(error).toHaveTextContent("Не удалось отправить отчёт");
    expect(error).toHaveTextContent("Что нужно исправить:");
    expect(error).toHaveTextContent("Обязательный раздел «Введение» отсутствует.");
    expect(error).toHaveTextContent("Обязательный раздел «Заключение» отсутствует.");
  });

  it("shows a network error beside the report when submission cannot reach the server", async () => {
    vi.spyOn(api, "get").mockResolvedValue(response([report], 1));
    vi.spyOn(api, "post").mockRejectedValue({ code: "ERR_NETWORK", request: {} });
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Отправить на проверку" }));

    const error = await screen.findByRole("alert");
    expect(error).toHaveTextContent("Не удалось отправить отчёт");
    expect(error).toHaveTextContent("Проверьте подключение к интернету или VPN и повторите попытку.");
  });
});
