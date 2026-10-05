import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "../../lib/api";
import { GroupDetailPage } from "./GroupDetailPage";

const group = {
  id: "group-1",
  name: "BK-2405",
  academic_year: "2026",
  students: [],
};

function paged(data: unknown[], total = data.length) {
  return {
    data,
    headers: {
      "x-total-count": String(total),
      "x-offset": "0",
      "x-limit": "25",
      "x-has-more": "false",
    },
  } as never;
}

function renderPage(initialEntry: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/groups/:groupId" element={<GroupDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("GroupDetailPage review queue", () => {
  it("opens a filtered queue from a deep link and renders its empty state", async () => {
    const get = vi.spyOn(api, "get").mockImplementation((url) => {
      const path = String(url);
      if (path.startsWith("/groups/group-1/reports/queue")) return Promise.resolve(paged([]));
      if (path.startsWith("/groups/group-1/internships")) return Promise.resolve(paged([]));
      if (path.startsWith("/groups/group-1/available-students")) return Promise.resolve(paged([]));
      if (path.startsWith("/groups/group-1/report-progress")) return Promise.resolve({ data: { total: 0, draft: 0, submitted: 0, under_review: 0, revision_required: 0, locked: 0 } } as never);
      if (path.startsWith("/groups/group-1?")) return Promise.resolve({ data: group, headers: paged([]).headers } as never);
      if (path.startsWith("/groups?")) return Promise.resolve(paged([]));
      throw new Error(`Unexpected request: ${path}`);
    });

    renderPage("/groups/group-1?tab=reports&status=SUBMITTED&deadline=overdue&student=Aya");

    expect(await screen.findByText("Нет отчётов, подходящих под выбранные фильтры.")).toBeInTheDocument();
    expect(screen.getByLabelText("Статус")).toHaveValue("SUBMITTED");
    expect(screen.getByLabelText("Срок")).toHaveValue("overdue");
    expect(screen.getByLabelText("Студент")).toHaveValue("Aya");
    expect(get).toHaveBeenCalledWith(expect.stringContaining("status=SUBMITTED"));
    expect(get).toHaveBeenCalledWith(expect.stringContaining("deadline=overdue"));
    expect(get).toHaveBeenCalledWith(expect.stringContaining("student=Aya"));
  });
});

describe("GroupDetailPage bulk student actions", () => {
  const groupWithStudents = {
    ...group,
    students: [
      { id: "membership-1", student_id: "student-1", full_name: "Алия", email: "aliya@example.edu" },
      { id: "membership-2", student_id: "student-2", full_name: "Бек", email: "bek@example.edu" },
    ],
  };

  function mockStudentPage(groupData = groupWithStudents) {
    return vi.spyOn(api, "get").mockImplementation((url) => {
      const path = String(url);
      if (path.startsWith("/groups/group-1/internships")) return Promise.resolve(paged([]));
      if (path.startsWith("/groups/group-1/available-students")) return Promise.resolve(paged([]));
      if (path.startsWith("/groups/group-1/report-progress")) return Promise.resolve({ data: { total: 0, draft: 0, submitted: 0, under_review: 0, revision_required: 0, locked: 0 } } as never);
      if (path.startsWith("/groups/group-1?")) return Promise.resolve({ data: groupData, headers: paged(groupData.students).headers } as never);
      if (path.startsWith("/groups?")) return Promise.resolve(paged([{ id: "group-1", name: "BK-2405", academic_year: "2026", student_count: 2 }, { id: "group-2", name: "BK-2406", academic_year: "2026", student_count: 0 }]));
      throw new Error(`Unexpected request: ${path}`);
    });
  }

  it("shows a confirmation and itemized partial result for bulk removal", async () => {
    mockStudentPage();
    const post = vi.spyOn(api, "post").mockResolvedValue({
      data: {
        succeeded_student_ids: ["student-1"],
        failed: [{ student_id: "student-2", code: "NOT_IN_SOURCE_GROUP" }],
      },
    } as never);

    renderPage("/groups/group-1?tab=students");

    fireEvent.click(await screen.findByLabelText("Выбрать Алия"));
    fireEvent.click(screen.getByLabelText("Выбрать Бек"));
    expect(screen.getByText("Выбрано 2 студента")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Удалить выбранных" }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Удалить выбранных студентов?")).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Удалить выбранных" }));

    await waitFor(() => expect(post).toHaveBeenCalledWith("/groups/group-1/students/bulk-remove", { student_ids: ["student-1", "student-2"] }));
    expect(await screen.findByText("Выполнено: успешно — 1, с ошибкой — 1.")).toBeInTheDocument();
    expect(screen.getAllByText("Алия")).toHaveLength(2);
    expect(screen.getByText("Бек: Студент больше не состоит в этой группе.")).toBeInTheDocument();
  });

  it("sends selected students to the chosen group only after confirmation", async () => {
    mockStudentPage();
    const post = vi.spyOn(api, "post").mockResolvedValue({ data: { succeeded_student_ids: ["student-1"], failed: [] } } as never);

    renderPage("/groups/group-1?tab=students");

    fireEvent.click(await screen.findByLabelText("Выбрать Алия"));
    fireEvent.change(screen.getByLabelText("Перевести выбранных в…"), { target: { value: "group-2" } });
    fireEvent.click(screen.getByRole("button", { name: "Перевести выбранных" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Перевести выбранных студентов?")).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();

    fireEvent.click(within(dialog).getByRole("button", { name: "Перевести выбранных" }));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/groups/group-1/students/bulk-transfer", { student_ids: ["student-1"], target_group_id: "group-2" }));
    expect(await screen.findByText("Выполнено: успешно — 1, с ошибкой — 0.")).toBeInTheDocument();
  });
});
