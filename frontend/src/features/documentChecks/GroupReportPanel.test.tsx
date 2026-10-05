import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { api } from "../../lib/api";
import { changeLocale } from "../../i18n";
import { GroupReportPanel } from "./GroupReportPanel";
import type { GroupReport } from "./groupReportApi";

const base = "/document-checks/teacher/groups/group/reports";
const finding = { id: "finding-1", rule_type: "PAGE_FORMAT_MARGINS" as const, location: { paragraph_index: 8 }, actual: { value: 10, unit: "mm" }, expected: { value: 20, unit: "mm" } };
const report: GroupReport = { id: "report-1", group_id: "group", locale: "ru", revision: 1, created_at: "2026-10-03T10:00:00Z", generated_at: null,
  snapshot: { group_name: "БК 2405", captured_at: "2026-10-03T10:00:00Z", skipped_works: 1,
    summary: { total_works: 30, reviewed_works: 12, pending_works: 18, included_works: 12, truncated_works: 2,
      violations: [{ rule_type: "PAGE_FORMAT_MARGINS", violations_count: 10, works_count: 1 }] },
    remarks: [{ submission_id: "doc-1", text: "Личное замечание Иванову" }] },
  content: { title: "Результаты проверки работ группы БК 2405", introduction: "", conclusions: "", selected_rule_types: ["PAGE_FORMAT_MARGINS"],
    finding_ids: [], remark_submission_ids: [], examples: [], remarks: [] } };
let client: QueryClient;
function paged(items: unknown[], total = items.length) { return { data: items, headers: { "x-total-count": String(total), "x-offset": "0", "x-limit": "25", "x-has-more": "false" } } as never; }
function setup(includedWorks = 12) {
  client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(<QueryClientProvider client={client}><GroupReportPanel groupId="group" includedWorks={includedWorks} /></QueryClientProvider>);
}
function mocks() {
  const get = vi.spyOn(api, "get").mockImplementation(async path => {
    if (String(path).includes("/findings")) return paged([finding], 40);
    if (String(path).includes("offset=")) return paged([]);
    return { data: report } as never;
  });
  const post = vi.spyOn(api, "post").mockResolvedValue({ data: report } as never);
  return { get, post };
}
beforeEach(async () => { await changeLocale("ru"); });
afterEach(() => { client?.clear(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it("explains why generation is unavailable and still loads saved report history", async () => {
  mocks(); setup(0);
  expect(screen.getByRole("button", { name: "Сформировать презентацию отчёта о проверке" })).toBeDisabled();
  expect(screen.getByText(/сначала завершите хотя бы одну/)).toBeVisible();
  await screen.findByText("Сохранённых отчётов пока нет.");
});

it("saves explicit choices, previews the persisted snapshot and exports its exact revision", async () => {
  const { get } = mocks();
  const put = vi.spyOn(api, "put").mockImplementation(async (_path, payload) => {
    const value = payload as GroupReport["content"];
    return { data: { ...report, revision: 2, content: { ...report.content, ...value, examples: [finding] } } } as never;
  });
  setup(); fireEvent.click(screen.getByRole("button", { name: "Сформировать презентацию отчёта о проверке" }));
  await screen.findByLabelText("Выводы преподавателя");
  expect(screen.getByText(/Проверена только часть группы: 12 из 30/)).toBeVisible();
  expect(screen.getByText(/Список findings ограничен у 2/)).toBeVisible();
  expect(screen.getByRole("checkbox", { name: /Личное замечание Иванову/ })).not.toBeChecked();
  fireEvent.click(await screen.findByRole("checkbox", { name: "Пример 1" }));
  fireEvent.change(screen.getByLabelText("Выводы преподавателя"), { target: { value: "Дополнить проверку группы" } });
  fireEvent.click(screen.getByRole("button", { name: "Предпросмотр содержания" }));
  const preview = await screen.findByRole("article", { name: "Предпросмотр содержания" });
  expect(within(preview).getByText("Дополнить проверку группы")).toBeVisible();
  expect(within(preview).queryByText(/Иванову/)).not.toBeInTheDocument();
  expect(put.mock.calls[0][1]).toMatchObject({ revision: 1, finding_ids: ["finding-1"], remark_submission_ids: [] });
  const post = vi.mocked(api.post).mockResolvedValue({ data: { ...report, revision: 2, generated_at: "2026-10-03T10:01:00Z" } } as never);
  get.mockResolvedValue({ data: new Blob(["pptx"]) } as never);
  vi.stubGlobal("URL", { createObjectURL: vi.fn().mockReturnValue("blob:test"), revokeObjectURL: vi.fn() });
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  fireEvent.click(screen.getByRole("button", { name: "Сформировать и скачать PPTX" }));
  await screen.findByRole("button", { name: "Скачать PPTX повторно" });
  expect(post).toHaveBeenLastCalledWith(`${base}/report-1/export`, { revision: 2 });
  expect(get).toHaveBeenCalledWith(`${base}/report-1/download`, { responseType: "blob" });
});

it("keeps text after failed save and reuses an uncertain create key", async () => {
  const { post } = mocks(); post.mockRejectedValueOnce(new Error("offline"));
  const put = vi.spyOn(api, "put").mockRejectedValue(new Error("conflict"));
  setup(); fireEvent.click(screen.getByRole("button", { name: "Сформировать презентацию отчёта о проверке" }));
  await screen.findByRole("alert");
  fireEvent.click(screen.getByRole("button", { name: "Сформировать презентацию отчёта о проверке" }));
  await screen.findByLabelText("Выводы преподавателя");
  expect(post.mock.calls[0][1]).toEqual(post.mock.calls[1][1]);
  fireEvent.change(screen.getByLabelText("Выводы преподавателя"), { target: { value: "Мой текст" } });
  fireEvent.click(screen.getByRole("button", { name: "Сохранить черновик" }));
  await waitFor(() => expect(put).toHaveBeenCalledTimes(1));
  expect(screen.getByLabelText("Выводы преподавателя")).toHaveValue("Мой текст");
  expect(screen.queryByRole("article")).not.toBeInTheDocument();
});

it.each(["ru", "kk", "en"])("creates a report using the active %s locale", async locale => {
  await changeLocale(locale as "ru" | "kk" | "en");
  const { post } = mocks(); setup();
  fireEvent.click(screen.getAllByRole("button")[0]);
  await waitFor(() => expect(post).toHaveBeenCalled());
  expect(post.mock.calls[0][1]).toMatchObject({ locale });
});
