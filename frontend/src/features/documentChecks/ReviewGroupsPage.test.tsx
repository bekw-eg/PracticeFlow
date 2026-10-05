import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { api } from "../../lib/api";
import { changeLocale } from "../../i18n";
import type { TeacherDocumentSubmission } from "../../types/api";
import { ReviewGroupPage, ReviewGroupsPage } from "./ReviewGroupsPage";
import { TeacherReviewPanel } from "./TeacherReviewPanel";
import { TeacherDocumentUpload } from "./TeacherDocumentUpload";

vi.mock("./DocumentChecksGate", () => ({ DocumentChecksGate: ({ children }: { children: ReactNode }) => children }));
const base = "/document-checks/teacher/groups";
const group = { id: "group-1", name: "БК 2405", description: "Работы", created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z" };
const submission: TeacherDocumentSubmission = {
  id: "doc-1", profile_version_id: "v1", student_label: "Алия", work_title: "Базы данных", work_type: "COURSEWORK", review_group_id: "group-1",
  original_filename: "work.docx", size_bytes: 1000, sha256: "a".repeat(64), detected_mime: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  submitted_at: "2026-01-01T00:00:00Z", preflight_schema_version: 1, created_at: "2026-01-01T00:00:00Z",
  job: { id: "run-1", status: "COMPLETED", queued_at: "2026-01-01T00:00:00Z", started_at: "2026-01-01T00:00:01Z", finished_at: "2026-01-01T00:00:02Z",
    run_number: 1, error_code: null, error_message: null, analyzer_version: "test", attempt_count: 1,
    result_summary: { analyzer_version: "test", rules_total: 1, rules_evaluated: 1, rules_skipped: 0, findings_count: 10, findings_truncated: false } },
};
const summary = { total_works: 30, pending_works: 26, reviewed_works: 4, included_works: 4, truncated_works: 0,
  violations: [{ rule_type: "PAGE_FORMAT_MARGINS", violations_count: 10, works_count: 1 }] };
const profile = { id: "p1", name: "Стандарт", versions: [{ id: "v1", state: "PUBLISHED", executable_rule_count: 1, version_number: 1 }] };
const clients: QueryClient[] = [];
function paged(items: unknown[], total = items.length, offset = 0) {
  return { data: items, headers: { "x-total-count": String(total), "x-offset": String(offset), "x-limit": "25", "x-has-more": String(offset + 25 < total) } } as never;
}
function setup(element?: ReactNode, initial = "/review-groups/group-1") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  clients.push(client);
  const view = render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[initial]}>
    {element ?? <Routes><Route path="/review-groups" element={<ReviewGroupsPage />} /><Route path="/review-groups/:groupId" element={<ReviewGroupPage />} /></Routes>}
  </MemoryRouter></QueryClientProvider>);
  return { client, ...view };
}
function mockGroup() {
  return vi.spyOn(api, "get").mockImplementation(async url => {
    const path = String(url);
    if (path === `${base}/group-1`) return { data: group } as never;
    if (path === `${base}/group-1/summary`) return { data: summary } as never;
    if (path.startsWith(`${base}/group-1/reports`)) return paged([]);
    if (path.includes("/works")) return paged([submission], 30, Number(new URL(path, "http://test").searchParams.get("offset")));
    if (path.startsWith("/check-profiles")) return paged([profile]);
    if (path.startsWith(base + "?")) return paged([]);
    throw new Error(path);
  });
}
beforeEach(async () => { await changeLocale("ru"); });
afterEach(() => { clients.forEach(client => client.clear()); clients.length = 0; vi.restoreAllMocks(); });

it("creates a group and opens it without student accounts", async () => {
  mockGroup();
  const post = vi.spyOn(api, "post").mockResolvedValue({ data: group } as never);
  setup(undefined, "/review-groups");
  await screen.findByText("Групп пока нет. Создайте первую группу выше.");
  fireEvent.change(screen.getByLabelText("Название группы"), { target: { value: " БК 2405 " } });
  fireEvent.click(screen.getByRole("button", { name: "Создать", exact: true }));
  await screen.findByRole("heading", { name: "БК 2405" });
  expect(post).toHaveBeenCalledWith(base, { name: "БК 2405", description: null });
});

it("edits group metadata and uses server pagination and review filtering without changing the summary", async () => {
  const get = mockGroup();
  const put = vi.spyOn(api, "put").mockResolvedValue({ data: { ...group, name: "БК 2406" } } as never);
  setup();
  await screen.findByRole("heading", { name: "БК 2405" });
  const report = screen.getByRole("region", { name: "Сводка ошибок группы" });
  expect(within(report).getByText(/В сводку включено работ: 4/)).toBeVisible();
  const cells = within(report).getAllByRole("cell");
  expect(cells[1]).toHaveTextContent("10");
  expect(cells[2]).toHaveTextContent("1");
  expect(screen.getByRole("link", { name: "Открыть работу" })).toHaveAttribute("href", "/document-checks/doc-1");
  fireEvent.click(screen.getAllByRole("button", { name: "Следующая страница" }).find(button => !button.hasAttribute("disabled"))!);
  await waitFor(() => expect(get).toHaveBeenCalledWith(`${base}/group-1/works?offset=25&limit=25`));
  fireEvent.change(screen.getByRole("combobox", { name: "Проверка преподавателем" }), { target: { value: "completed" } });
  await waitFor(() => expect(get).toHaveBeenCalledWith(`${base}/group-1/works?review_status=completed&offset=0&limit=25`));
  expect(within(report).getByText(/В сводку включено работ: 4/)).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Изменить группу" }));
  fireEvent.change(screen.getByLabelText("Название группы"), { target: { value: "БК 2406" } });
  fireEvent.click(screen.getByRole("button", { name: "Сохранить", exact: true }));
  await waitFor(() => expect(put).toHaveBeenCalledWith(`${base}/group-1`, { name: "БК 2406", description: "Работы" }));
});

it("shows an empty group and does not describe unreviewed works as error-free", async () => {
  vi.spyOn(api, "get").mockImplementation(async url => {
    const path = String(url);
    if (path.endsWith("/summary")) return { data: { ...summary, included_works: 0, violations: [] } } as never;
    if (path === `${base}/group-1`) return { data: group } as never;
    return paged([]);
  });
  setup();
  expect(await screen.findByText("Для сводки пока нет работ с завершённой проверкой преподавателя.")).toBeVisible();
  expect(screen.getByText("Работ пока нет. Загрузите первый DOCX в эту группу.")).toBeVisible();
});

it("shows a failed group load and can retry", async () => {
  vi.spyOn(api, "get").mockRejectedValue(new Error("offline"));
  setup();
  expect(await screen.findByRole("button", { name: "Повторить" })).toBeVisible();
  expect(screen.queryByText("БК 2405")).not.toBeInTheDocument();
});

it("uploads group metadata through the original endpoint and reuses an uncertain upload key", async () => {
  vi.spyOn(api, "get").mockResolvedValue(paged([profile]));
  const post = vi.spyOn(api, "post").mockRejectedValueOnce(new Error("offline")).mockResolvedValue({ data: submission } as never);
  setup(<TeacherDocumentUpload groupId="group-1" />);
  await screen.findByRole("option", { name: /Стандарт/ });
  fireEvent.change(screen.getByRole("combobox", { name: "Профиль проверки" }), { target: { value: "v1" } });
  fireEvent.change(screen.getByLabelText("Студент"), { target: { value: "Алия" } });
  fireEvent.change(screen.getByLabelText("Название работы"), { target: { value: "Базы данных" } });
  const file = screen.getByLabelText("Документ Word (.docx)");
  fireEvent.change(file, { target: { files: [new File(["original"], "work.docx")] } });
  fireEvent.submit(file.closest("form")!);
  await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
  await waitFor(() => expect(screen.getByRole("button", { name: "Начать проверку" })).toBeEnabled());
  fireEvent.submit(file.closest("form")!);
  await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
  expect(post.mock.calls[0][0]).toBe("/document-checks/teacher/submissions");
  const data = post.mock.calls[0][1] as FormData;
  expect(data.get("review_group_id")).toBe("group-1");
  expect(data.get("work_title")).toBe("Базы данных");
  expect(data.get("work_type")).toBe("COURSEWORK");
  expect(post.mock.calls[0][2]?.headers?.["Idempotency-Key"]).toBe(post.mock.calls[1][2]?.headers?.["Idempotency-Key"]);
});

it("keeps unsaved remarks after failure and completes the exact viewed older run", async () => {
  const put = vi.spyOn(api, "put").mockRejectedValue(new Error("offline"));
  const post = vi.spyOn(api, "post").mockResolvedValue({ data: { revision: 1, remarks: "Поля", completed_at: "2026-01-01T00:00:03Z", completed_job_id: "run-1", completed_by_teacher_id: "teacher" } } as never);
  setup(<TeacherReviewPanel submission={{ ...submission, job: { ...submission.job, id: "run-2", run_number: 2 } }} viewedJob={submission.job} ready onShowReviewedRun={vi.fn()} />);
  fireEvent.change(screen.getByLabelText("Замечания преподавателя"), { target: { value: "Поля" } });
  fireEvent.click(screen.getByRole("button", { name: "Сохранить замечания" }));
  await waitFor(() => expect(put).toHaveBeenCalledTimes(1));
  await waitFor(() => expect(screen.getByRole("button", { name: "Завершить проверку" })).toBeEnabled());
  expect(screen.getByLabelText("Замечания преподавателя")).toHaveValue("Поля");
  fireEvent.click(screen.getByRole("button", { name: "Завершить проверку" }));
  await waitFor(() => expect(post).toHaveBeenCalledWith("/document-checks/teacher/submissions/doc-1/review/complete", { revision: 0, remarks: "Поля", job_id: "run-1" }));
});

it("requires a loaded completed result and makes the pinned review available after a rerun", () => {
  const show = vi.fn();
  const { rerender } = setup(<TeacherReviewPanel submission={submission} ready={false} onShowReviewedRun={show} />);
  expect(screen.getByRole("button", { name: "Завершить проверку" })).toBeDisabled();
  const client = clients[0];
  rerender(<QueryClientProvider client={client}><TeacherReviewPanel submission={{ ...submission, teacher_review: {
    revision: 1, remarks: "Проверено", completed_at: "2026-01-01T00:00:03Z", completed_by_teacher_id: "teacher", completed_job_id: "old-run",
  } }} viewedJob={submission.job} ready onShowReviewedRun={show} /></QueryClientProvider>);
  expect(screen.queryByRole("button", { name: "Завершить проверку" })).not.toBeInTheDocument();
  expect(screen.getByLabelText("Замечания преподавателя")).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Показать подтверждённый запуск" }));
  expect(show).toHaveBeenCalledWith("old-run");
});
