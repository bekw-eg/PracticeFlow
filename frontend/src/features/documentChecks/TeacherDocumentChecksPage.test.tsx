import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { api } from "../../lib/api";
import { changeLocale } from "../../i18n";
import { AppShell } from "../../app/AppShell";
import { AuthContext, type AuthContextValue } from "../auth/authContextValue";
import { TeacherDocumentChecksPage } from "./TeacherDocumentChecksPage";
import type { DocumentCheckFinding, TeacherDocumentSubmission } from "../../types/api";

vi.mock("../../components/NotificationBell", () => ({ NotificationBell: () => null }));
vi.mock("../../components/OrganizationSwitcher", () => ({ OrganizationSwitcher: () => null }));

const teacherSubmission: TeacherDocumentSubmission = {
  id: "teacher-submission-1", profile_version_id: "version-1", student_label: "Алия",
  original_filename: "report.docx", size_bytes: 1234, sha256: "b".repeat(64),
  detected_mime: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  submitted_at: "2026-01-02T12:00:00Z", preflight_schema_version: 1, created_at: "2026-01-02T12:00:00Z",
  job: { id: "teacher-job-1", status: "QUEUED", queued_at: "2026-01-02T12:00:00Z", started_at: null, finished_at: null, error_code: null, error_message: null, analyzer_version: null, attempt_count: 0, result_summary: null },
};

function paged(data: unknown[], total = data.length, offset = 0) {
  return { data, headers: { "x-total-count": String(total), "x-offset": String(offset), "x-limit": "25", "x-has-more": String(offset + data.length < total) } } as never;
}

function auth(enabled = true, role: "STUDENT" | "TEACHER" = "TEACHER"): AuthContextValue {
  return {
    user: { user_id: "user-1", organization_id: "org-1", full_name: "Алия", email: "aliya@example.edu", role, features: { document_check_enabled: enabled, legacy_document_editor_enabled: false } },
    isLoading: false, login: vi.fn(), logout: vi.fn(), switchOrganization: vi.fn(), completeMfaSession: vi.fn(),
  };
}

function page(element: ReactNode, authValue = auth()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<AuthContext.Provider value={authValue}><QueryClientProvider client={client}><MemoryRouter initialEntries={["/document-checks"]}><Routes>
    <Route path="/document-checks" element={element} />
  </Routes></MemoryRouter></QueryClientProvider></AuthContext.Provider>);
}

afterEach(async () => { vi.restoreAllMocks(); await changeLocale("ru"); });

describe("teacher-only document checks", () => {
  it("uploads a DOCX without a student account or assignment", async () => {
    const profile = {
      id: "profile-1", name: "Дипломная работа", description: null, created_at: "2026-01-01T00:00:00Z",
      versions: [{ id: "version-1", profile_id: "profile-1", version_number: 1, state: "PUBLISHED", notes: null, published_at: "2026-01-01T00:00:00Z", retired_at: null, created_at: "2026-01-01T00:00:00Z", executable_rule_count: 1 }],
    };
    vi.spyOn(api, "get").mockImplementation((url) => Promise.resolve(String(url).startsWith("/check-profiles") ? paged([profile]) : paged([])));
    const post = vi.spyOn(api, "post").mockResolvedValue({ data: teacherSubmission } as never);
    page(<TeacherDocumentChecksPage />);
    expect(await screen.findByText("Аккаунт студента и назначение группе не требуются.")).toBeInTheDocument();
    const profileSelect = await screen.findByRole("combobox", { name: "Профиль проверки" });
    fireEvent.change(profileSelect, { target: { value: "version-1" } });
    fireEvent.change(screen.getByRole("textbox", { name: "Студент или работа" }), { target: { value: "Алия" } });
    const input = screen.getByLabelText("Документ Word (.docx)");
    fireEvent.change(input, { target: { files: [new File(["original teacher bytes"], "report.docx")] } });
    fireEvent.submit(input.closest("form")!);
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(post.mock.calls[0][0]).toBe("/document-checks/teacher/submissions");
    expect((post.mock.calls[0][1] as FormData).get("profile_version_id")).toBe("version-1");
    expect((post.mock.calls[0][1] as FormData).get("student_label")).toBe("Алия");
  });

  it("loads findings only from the teacher endpoint", async () => {
    const completed: TeacherDocumentSubmission = { ...teacherSubmission, job: {
      ...teacherSubmission.job, status: "COMPLETED", analyzer_version: "phase-2.2.1", attempt_count: 1,
      started_at: "2026-01-02T12:00:01Z", finished_at: "2026-01-02T12:00:02Z",
      result_summary: { analyzer_version: "phase-2.2.1", rules_total: 1, rules_evaluated: 1, rules_skipped: 0, findings_count: 1, findings_truncated: false },
    } };
    const finding: DocumentCheckFinding = {
      id: "finding-1", check_rule_id: "rule-1", sequence: 1, rule_type: "FONTS_SIZES",
      category: "formatting", severity: "ERROR", code: "FONT_NOT_ALLOWED", property_name: "font",
      location: { paragraph_index: 1 }, expected: { allowed: ["Arial"] }, actual: { value: "Times New Roman" }, finding_schema_version: 1,
    };
    const get = vi.spyOn(api, "get").mockImplementation((url) => {
      const path = String(url);
      if (path.includes("/findings")) return Promise.resolve(paged([finding]));
      if (path.startsWith("/check-profiles")) return Promise.resolve(paged([]));
      return Promise.resolve(paged([completed]));
    });
    page(<TeacherDocumentChecksPage />);
    expect(await screen.findByText("1 замечание")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Показать замечания" }));
    expect(await screen.findByText("Недопустимый шрифт")).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith("/document-checks/teacher/submissions/teacher-submission-1/findings?job_id=teacher-job-1&offset=0&limit=25");
  });

  it("never shows document checks in student navigation", () => {
    page(<AppShell />, auth(true, "STUDENT"));
    const navigation = within(screen.getAllByRole("navigation")[0]);
    expect(navigation.queryByRole("link", { name: "Проверка документов" })).not.toBeInTheDocument();
  });

  it.each([true, false])("follows the teacher feature flag (enabled=%s)", (enabled) => {
    page(<AppShell />, auth(enabled));
    const navigation = within(screen.getAllByRole("navigation")[0]);
    expect(Boolean(navigation.queryByRole("link", { name: "Проверка документов" }))).toBe(enabled);
  });
});
