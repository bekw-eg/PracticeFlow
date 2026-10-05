import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "../../lib/api";
import { formatDate } from "../../i18n/formatters";
import * as toast from "../../lib/toast";
import { TeacherReportPage } from "./TeacherReportPage";

const report = {
  id: "report-1",
  internship_id: "internship-1",
  student_id: "student-1",
  status: "UNDER_REVIEW",
  current_version_id: "version-1",
  created_at: "2026-06-01T09:00:00Z",
  deadline: "2026-07-20",
  internship_title: "Летняя практика",
  versions: [{ id: "version-1", version_number: 1, submitted_at: "2026-07-19T10:00:00Z" }],
};

const documentResponse = {
  document: {
    schema_version: 1,
    meta: {
      page_size: "A4", orientation: "portrait", margins: { top_mm: 20, bottom_mm: 20, left_mm: 20, right_mm: 20 },
      default_font: "Arial", default_font_size: 12, line_spacing: 1.5, styles: {}, numbering: { enabled: false, start_number: 1, style: "decimal" },
    },
    title_page: null,
    header: { enabled: false, blocks: [] },
    footer: { enabled: false, blocks: [] },
    sections: [],
  },
  numbering: {},
  editable: false,
  revision: 1,
};

const headers = { "x-total-count": "0", "x-offset": "0", "x-limit": "25", "x-has-more": "false" };

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}><MemoryRouter initialEntries={["/groups/group-1/reports/report-1"]}><Routes><Route path="/groups/:groupId/reports/:reportId" element={<TeacherReportPage />} /></Routes></MemoryRouter></QueryClientProvider>);
}

function mockPage() {
  return vi.spyOn(api, "get").mockImplementation((url) => {
    const path = String(url);
    if (path.startsWith("/groups/group-1/reports/report-1/next-in-queue")) return Promise.resolve({ data: null } as never);
    if (path.startsWith("/groups/group-1?")) return Promise.resolve({ data: { id: "group-1", name: "BK-2405", academic_year: "2026", students: [{ id: "membership-1", student_id: "student-1", full_name: "Алия", email: "aliya@example.edu" }] }, headers } as never);
    if (path === "/reports/report-1") return Promise.resolve({ data: report } as never);
    if (path === "/reports/report-1/document") return Promise.resolve({ data: documentResponse } as never);
    if (path.startsWith("/reports/report-1/history")) return Promise.resolve({ data: [], headers } as never);
    if (path.startsWith("/reports/report-1/comments")) return Promise.resolve({ data: [], headers } as never);
    throw new Error(`Unexpected request: ${path}`);
  });
}

async function openApprovalDialog() {
  fireEvent.click(await screen.findByRole("button", { name: "Утвердить и закрыть" }));
  return screen.findByRole("dialog");
}

afterEach(() => vi.restoreAllMocks());

describe("TeacherReportPage review actions", () => {
  it("requires confirmation before approving and closing a report", async () => {
    mockPage();
    const post = vi.spyOn(api, "post").mockResolvedValue({ data: { ...report, status: "LOCKED" } } as never);
    const showToast = vi.spyOn(toast, "showToast");
    renderPage();

    const dialog = await openApprovalDialog();
    expect(post).not.toHaveBeenCalled();
    expect(within(dialog).getByText("Алия")).toBeInTheDocument();
    expect(within(dialog).getByText("Летняя практика")).toBeInTheDocument();
    expect(within(dialog).getByText(formatDate("2026-07-20", "ru"))).toBeInTheDocument();
    expect(within(dialog).getByText("После утверждения отчёт будет заблокирован и его нельзя будет изменить.")).toBeInTheDocument();

    fireEvent.click(within(dialog).getByRole("button", { name: "Утвердить и закрыть" }));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/reports/report-1/review/approve"));
    expect(showToast).toHaveBeenCalledWith("Отчёт утверждён и заблокирован.");
  });

  it("cancels approval without calling the API", async () => {
    mockPage();
    const post = vi.spyOn(api, "post");
    renderPage();

    const dialog = await openApprovalDialog();
    fireEvent.click(within(dialog).getByRole("button", { name: "Отмена" }));

    expect(post).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("does not allow a revision request without a comment", async () => {
    mockPage();
    const post = vi.spyOn(api, "post");
    renderPage();

    const button = await screen.findByRole("button", { name: "Вернуть на доработку" });
    expect(button).toBeDisabled();
    expect(screen.getByText("Для возврата на доработку нужно добавить комментарий.")).toBeInTheDocument();
    fireEvent.click(button);
    expect(post).not.toHaveBeenCalled();
  });

  it("keeps the confirmation open and shows API feedback when approval fails", async () => {
    mockPage();
    vi.spyOn(api, "post").mockRejectedValue({ code: "ERR_NETWORK", request: {} });
    renderPage();

    const dialog = await openApprovalDialog();
    fireEvent.click(within(dialog).getByRole("button", { name: "Утвердить и закрыть" }));

    const error = await within(dialog).findByRole("alert");
    expect(error).toHaveTextContent("Не удалось выполнить действие проверки.");
    expect(error).toHaveTextContent("Проверьте подключение к интернету или VPN и повторите попытку.");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});
