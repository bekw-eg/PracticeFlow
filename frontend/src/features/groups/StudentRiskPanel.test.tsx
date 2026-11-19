import { fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "../../lib/api";
import type { GroupStudentRisk, StudentRiskItem } from "../../types/api";
import { StudentRiskPanel } from "./StudentRiskPanel";

afterEach(() => vi.restoreAllMocks());

function item(overrides: Partial<StudentRiskItem>): StudentRiskItem {
  return {
    student_id: "s1", student_name: "Аян Серіков", internship_id: "i1", internship_title: "Производственная практика",
    report_id: "r1", report_status: "DRAFT", deadline: "2026-06-21", completion_percent: 40, days_since_activity: 6,
    level: "GREEN", reasons: [], ...overrides,
  };
}

function renderPanel(data: GroupStudentRisk | Error) {
  vi.spyOn(api, "get").mockImplementation(() => (data instanceof Error ? Promise.reject(data) : Promise.resolve({ data } as never)));
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}><StudentRiskPanel groupId="group-1" /></QueryClientProvider>);
}

describe("StudentRiskPanel", () => {
  it("lists students needing attention first, with text labels and translated reasons", async () => {
    renderPanel({
      red: 1, yellow: 1, green: 1,
      items: [
        item({ report_id: "r1", student_name: "Аян Серіков", level: "RED", reasons: ["OVERDUE"], completion_percent: 10 }),
        item({ report_id: "r2", student_name: "Дана Ким", level: "YELLOW", reasons: ["NO_RECENT_ACTIVITY", "BEHIND_SCHEDULE"], days_since_activity: 7 }),
        item({ report_id: "r3", student_name: "Ерлан Бек", level: "GREEN", report_status: "SUBMITTED" }),
      ],
    });

    expect(await screen.findByRole("heading", { name: "Прогресс студентов" })).toBeInTheDocument();
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows).toHaveLength(2); // the on-track student is hidden by the default filter
    expect(within(rows[0]).getByText("Аян Серіков")).toBeInTheDocument();
    expect(within(rows[0]).getByText("Срок прошёл, а отчёт не сдан")).toBeInTheDocument();
    expect(rows[0].querySelector('[data-risk-level="RED"]')).toHaveTextContent("Нужно внимание");
    expect(within(rows[1]).getByText("Несколько дней нет правок")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Отчёт отстаёт от графика практики")).toBeInTheDocument();
    expect(within(rows[1]).getByText("7 дн. назад")).toBeInTheDocument();
  });

  it("can show everyone, including students who are on track", async () => {
    renderPanel({ red: 1, yellow: 0, green: 1, items: [item({ report_id: "r1", level: "RED", reasons: ["OVERDUE"] }), item({ report_id: "r2", student_name: "Ерлан Бек", level: "GREEN" })] });

    await screen.findByRole("heading", { name: "Прогресс студентов" });
    expect(screen.queryByText("Ерлан Бек")).not.toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Только студенты, которым нужно внимание"));
    expect(screen.getByText("Ерлан Бек")).toBeInTheDocument();
  });

  it("says so when everyone is on track instead of showing an empty table", async () => {
    renderPanel({ red: 0, yellow: 0, green: 2, items: [item({ report_id: "r1" }), item({ report_id: "r2" })] });

    expect(await screen.findByRole("status")).toHaveTextContent("Все идут по графику");
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("renders nothing when the group has no open reports", async () => {
    const { container } = renderPanel({ red: 0, yellow: 0, green: 0, items: [] });
    await vi.waitFor(() => expect(api.get).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it("shows a retryable error when loading fails", async () => {
    renderPanel(new Error("boom"));
    expect(await screen.findByText("Не удалось загрузить прогресс студентов.")).toBeInTheDocument();
  });
});
