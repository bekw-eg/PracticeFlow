import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "../../lib/api";
import { DirectorDashboardPage } from "./DirectorDashboard";

const dashboard = {
  organization: { id: "org-1", name: "Колледж PracticeFlow", slug: "practiceflow" },
  groups_count: 1,
  students_count: 18,
  teachers_count: 1,
  groups: [{
    id: "group-1",
    name: "BK-2405",
    academic_year: "2026–2027",
    student_count: 18,
  }],
  teacher_loads: [{
    id: "teacher-1",
    full_name: "Айгуль Серикова",
    groups_count: 1,
  }],
};

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <DirectorDashboardPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("DirectorDashboardPage", () => {
  it("shows read-only tenant aggregates and only safe administration drill-downs", async () => {
    vi.spyOn(api, "get").mockResolvedValue({ data: dashboard } as never);

    renderPage();

    expect(await screen.findByRole("heading", { name: "Колледж PracticeFlow" })).toBeInTheDocument();
    expect(screen.getByText("BK-2405")).toBeInTheDocument();
    expect(screen.getByText("Айгуль Серикова")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Открыть управление группами" })).toHaveAttribute("href", "/admin?view=management&tab=groups");
    expect(screen.getByRole("link", { name: "Открыть список участников" })).toHaveAttribute("href", "/admin?view=management&tab=members");
    expect(api.get).toHaveBeenCalledWith("/director/dashboard");
  });

  it("shows an empty state when the organization has no operational data", async () => {
    vi.spyOn(api, "get").mockResolvedValue({ data: { ...dashboard, groups_count: 0, students_count: 0, teachers_count: 0, groups: [], teacher_loads: [] } } as never);

    renderPage();

    expect(await screen.findByText("Данных по учебному процессу пока нет")).toBeInTheDocument();
  });

  it("shows a loading state while the dashboard request is pending", () => {
    vi.spyOn(api, "get").mockImplementation(() => new Promise(() => {}) as never);

    renderPage();

    expect(screen.getByRole("status")).toHaveTextContent("Загрузка данных учебного процесса…");
  });

  it("shows a retryable error state", async () => {
    const get = vi.spyOn(api, "get").mockRejectedValue(new Error("offline"));

    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent("Не удалось загрузить панель учебного процесса. Повторите попытку.");
    expect(screen.getByRole("button", { name: "Повторить" })).toBeInTheDocument();
    expect(get).toHaveBeenCalledTimes(1);
  });
});
