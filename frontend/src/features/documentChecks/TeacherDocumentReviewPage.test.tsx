import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { api } from "../../lib/api";
import { changeLocale } from "../../i18n";
import type { DocumentCheckJob, DocumentSettings, TeacherDocumentSubmission } from "../../types/api";
import { TeacherDocumentReviewPage } from "./TeacherDocumentReviewPage";

vi.mock("./DocumentChecksGate", () => ({ DocumentChecksGate: ({ children }: { children: ReactNode }) => children }));
vi.mock("./PaginatedDocument", () => ({ PaginatedDocument: ({ onParagraphSelect }: { onParagraphSelect: (paragraph: { index: number; text: string }) => void }) =>
  <button onClick={() => onParagraphSelect({ index: 2, text: "Введение" })}>Select source paragraph</button> }));

const base = "/document-checks/teacher/submissions/doc-1";
const job: DocumentCheckJob = {
  id: "run-1", run_number: 1, settings_revision: 1, status: "COMPLETED", queued_at: "2026-01-01T00:00:00Z",
  started_at: "2026-01-01T00:00:01Z", finished_at: "2026-01-01T00:00:02Z", error_code: null, error_message: null,
  analyzer_version: "phase-2.4.0", attempt_count: 1,
  result_summary: { analyzer_version: "phase-2.4.0", rules_total: 1, rules_evaluated: 1, rules_skipped: 0,
    findings_count: 0, findings_truncated: false, first_page_exclusion: "APPLIED" },
};
const initial: DocumentSettings = { submission_id: "doc-1", revision: 1, updated_at: "2026-01-01T00:00:00Z",
  paragraph_overrides: {}, rules: [{ rule_type: "FONTS_SIZES", category: "formatting", severity: "ERROR", enabled: true,
    sort_order: 0, config_schema_version: 1, config: { allowed_fonts: ["Times New Roman"], min_size_pt: 14, max_size_pt: 14 } }] };
const document: TeacherDocumentSubmission = {
  id: "doc-1", profile_version_id: "profile-1", student_label: null, original_filename: "coursework.docx", size_bytes: 1000,
  sha256: "a".repeat(64), detected_mime: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  submitted_at: "2026-01-01T00:00:00Z", preflight_schema_version: 1, created_at: "2026-01-01T00:00:00Z",
  job, latest_completed_job: job,
};

function setup() {
  let saved = structuredClone(initial);
  let current = structuredClone(document);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  vi.spyOn(api, "get").mockImplementation(async url => {
    const path = String(url);
    if (path === `${base}/settings`) return { data: structuredClone(saved) } as never;
    if (path === `${base}/paragraphs`) return { data: [{ paragraph_index: 2, automatic_type: "HEADING_1", paragraph_type: "HEADING_1", source: "HEURISTIC", excluded: false }] } as never;
    if (path === `${base}/preview`) return { data: { html: "", paragraph_count: 2 } } as never;
    if (path.includes("/findings")) return { data: [], headers: { "x-has-more": "false", "x-total-count": "0" } } as never;
    if (path.includes("/runs?")) return { data: [current.job, ...(current.job.id !== job.id ? [job] : [])], headers: { "x-has-more": "false" } } as never;
    if (path === base) return { data: structuredClone(current) } as never;
    throw new Error(`Unexpected request ${path}`);
  });
  const put = vi.spyOn(api, "put").mockImplementation(async (_url, body) => {
    saved = { ...saved, ...(body as Partial<DocumentSettings>), revision: saved.revision + 1 };
    return { data: structuredClone(saved) } as never;
  });
  const post = vi.spyOn(api, "post").mockImplementation(async () => {
    current = { ...current, job: { ...job, id: "run-2", run_number: 2, settings_revision: saved.revision,
      status: "QUEUED", started_at: null, finished_at: null, result_summary: null } };
    return { data: current.job } as never;
  });
  const page = render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/document-checks/doc-1"]}>
    <Routes><Route path="/document-checks/:submissionId" element={<TeacherDocumentReviewPage />} /></Routes>
  </MemoryRouter></QueryClientProvider>);
  return { client, put, post, ...page };
}

beforeEach(async () => { await changeLocale("ru"); });
afterEach(() => { vi.restoreAllMocks(); });

it("keeps edits after save failure and saves manual classification without starting analysis", async () => {
  const { put, post, client } = setup();
  await screen.findByText("Сохранено для документа · версия 1");
  fireEvent.click(screen.getByRole("tab", { name: "Правила" }));
  fireEvent.click(screen.getByText("Select source paragraph"));
  fireEvent.change(screen.getByRole("combobox", { name: "Считать этот абзац" }), { target: { value: "BODY" } });
  fireEvent.change(screen.getByRole("spinbutton", { name: "Минимальный размер, пт" }), { target: { value: "13" } });
  expect(post).not.toHaveBeenCalled();
  expect(put).not.toHaveBeenCalled();
  put.mockRejectedValueOnce(new Error("offline"));
  fireEvent.click(screen.getByRole("button", { name: "Сохранить", exact: true }));
  await screen.findByText(/Настройки не сохранены/);
  expect(screen.getByRole("spinbutton", { name: "Минимальный размер, пт" })).toHaveValue(13);
  expect(screen.getByRole("combobox", { name: "Считать этот абзац" })).toHaveValue("BODY");
  await client.invalidateQueries({ queryKey: ["document-settings", "doc-1"] });
  expect(screen.getByRole("spinbutton", { name: "Минимальный размер, пт" })).toHaveValue(13);
  fireEvent.click(screen.getByRole("button", { name: "Сохранить", exact: true }));
  await screen.findByText("Сохранено для документа · версия 2");
  expect(put.mock.calls[1][0]).toBe(`${base}/settings`);
  expect(put.mock.calls[1][1]).toMatchObject({ revision: 1, paragraph_overrides: { "2": "BODY" } });
  expect(post).not.toHaveBeenCalled();
  client.clear();
});

it("saves before rechecking, reuses an uncertain request key, and keeps completed findings while queued", async () => {
  const { put, post, client } = setup();
  await screen.findByText("Замечаний не найдено");
  fireEvent.click(screen.getByRole("tab", { name: "Правила" }));
  fireEvent.change(screen.getByRole("spinbutton", { name: "Минимальный размер, пт" }), { target: { value: "13" } });
  post.mockRejectedValueOnce(new Error("response lost"));
  fireEvent.click(screen.getByRole("button", { name: "Перепроверить" }));
  await screen.findByText(/Не удалось подтвердить запуск/);
  expect(put).toHaveBeenCalledTimes(1);
  expect(post.mock.calls[0][1]).toEqual({ revision: 2 });
  const key = post.mock.calls[0][2]?.headers?.["Idempotency-Key"];
  fireEvent.click(screen.getByRole("button", { name: "Перепроверить" }));
  await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
  expect(post.mock.calls[1][2]?.headers?.["Idempotency-Key"]).toBe(key);
  expect(put).toHaveBeenCalledTimes(1);
  await screen.findByText("Новая проверка выполняется. Пока показан предыдущий готовый результат.");
  expect(screen.getByText("Замечаний не найдено")).toBeVisible();
  expect(screen.getByRole("button", { name: "Перепроверить" })).toBeDisabled();
  client.clear();
});
