import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { api } from "../../lib/api";
import { changeLocale } from "../../i18n";
import { DisciplinesPage, DisciplinePage, TopicPage } from "./DisciplinePages";
import type { Discipline, TeachingMaterial, Topic } from "./types";

const auth = vi.hoisted(() => ({ user: { organization_id: "org-a", user_id: "teacher", role: "TEACHER" } }));
vi.mock("../auth/useAuth", () => ({ useAuth: () => auth }));
const dates = { created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z" };
const discipline: Discipline = { id: "d1", name: "Web Development", description: "Course", academic_year: "2026", is_archived: false, ...dates };
const topic: Topic = { id: "t1", discipline_id: "d1", title: "React Hooks", description: "Lecture",
  learning_goal: "Use useState and useEffect", position: 0, is_archived: false, ...dates };
const material: TeachingMaterial = { id: "m1", discipline_id: "d1", topic_id: "t1", title: "Lecture", original_filename: "lecture.pdf",
  content_type: "application/pdf", size_bytes: 100, sha256: "a".repeat(64), created_at: dates.created_at };
const clients: QueryClient[] = [];
function paged(items: unknown[], total = items.length) {
  return { data: items, headers: { "x-total-count": String(total), "x-offset": "0", "x-limit": "25", "x-has-more": String(total > 25) } } as never;
}
function setup(path = "/disciplines/d1/topics/t1") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  clients.push(client);
  const view = render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}><Routes>
    <Route path="/disciplines" element={<DisciplinesPage />} />
    <Route path="/disciplines/:disciplineId" element={<DisciplinePage />} />
    <Route path="/disciplines/:disciplineId/topics/:topicId" element={<TopicPage />} />
  </Routes></MemoryRouter></QueryClientProvider>);
  return { client, ...view };
}
function mockGet(materials: TeachingMaterial[] = []) {
  return vi.spyOn(api, "get").mockImplementation(async url => {
    const path = String(url);
    if (path === "/disciplines/d1") return { data: discipline } as never;
    if (path === "/topics/t1") return { data: topic } as never;
    if (path.endsWith("/groups")) return { data: [] } as never;
    if (path.startsWith("/topics/t1/materials?")) return paged(materials);
    if (path.includes("/topics?")) return paged([]);
    return paged([]);
  });
}
beforeEach(async () => {
  auth.user = { organization_id: "org-a", user_id: "teacher", role: "TEACHER" };
  await changeLocale("en");
});
afterEach(() => { clients.forEach(client => client.clear()); clients.length = 0; vi.restoreAllMocks(); });

it("creates a discipline, opens it, and creates a topic with its learning goal", async () => {
  mockGet();
  const post = vi.spyOn(api, "post").mockResolvedValueOnce({ data: discipline } as never).mockResolvedValue({ data: topic } as never);
  setup("/disciplines");
  await screen.findByText("No disciplines yet");
  fireEvent.change(screen.getByLabelText("Discipline name"), { target: { value: " Web Development " } });
  fireEvent.click(screen.getByRole("button", { name: "Create", exact: true }));
  await screen.findByRole("heading", { name: "Web Development" });
  expect(post).toHaveBeenCalledWith("/disciplines", { name: "Web Development", description: null, academic_year: null, group_ids: [] });
  fireEvent.change(screen.getByLabelText("Topic title"), { target: { value: "React Hooks" } });
  fireEvent.change(screen.getByLabelText("Learning goal"), { target: { value: "Use useState and useEffect" } });
  fireEvent.click(screen.getByRole("button", { name: "Create", exact: true }));
  await screen.findByRole("heading", { name: "React Hooks" });
  expect(screen.getByText("Use useState and useEffect")).toBeVisible();
  expect(post).toHaveBeenCalledWith("/disciplines/d1/topics", { title: "React Hooks", description: null, learning_goal: "Use useState and useEffect" });
});

it("shows loading and inaccessible resources without an upload form", async () => {
  vi.spyOn(api, "get").mockImplementation(() => new Promise(() => {}));
  const view = setup();
  expect(screen.getByRole("status")).toBeVisible();
  view.unmount();
  vi.restoreAllMocks();
  vi.spyOn(api, "get").mockRejectedValue({ isAxiosError: true, response: { status: 404, data: { detail: "missing" } } });
  setup();
  await screen.findByRole("alert");
  expect(screen.queryByLabelText("Material file")).not.toBeInTheDocument();
});

it("rejects unsupported and oversized files before any API upload", async () => {
  mockGet();
  const post = vi.spyOn(api, "post");
  setup();
  const input = await screen.findByLabelText("Material file");
  const form = input.closest("form")!;
  fireEvent.change(input, { target: { files: [new File(["bad"], "script.exe")] } });
  fireEvent.submit(form);
  expect(screen.getByText("Only PDF, DOCX and PPTX are supported.")).toBeVisible();
  const large = new File(["pdf"], "large.pdf");
  Object.defineProperty(large, "size", { value: 20 * 1024 * 1024 + 1 });
  fireEvent.change(input, { target: { files: [large] } });
  fireEvent.submit(form);
  expect(screen.getByText("The file exceeds 20 MiB.")).toBeVisible();
  expect(post).not.toHaveBeenCalled();
});

it("prevents duplicate submit, preserves the uncertain upload key, and refreshes materials", async () => {
  const get = mockGet();
  let reject: (reason?: unknown) => void = () => {};
  const post = vi.spyOn(api, "post").mockImplementationOnce(() => new Promise((_resolve, fail) => { reject = fail; }));
  setup();
  const input = await screen.findByLabelText("Material file");
  fireEvent.change(input, { target: { files: [new File(["%PDF"], "lecture.pdf", { type: "application/pdf" })] } });
  const form = input.closest("form")!;
  fireEvent.submit(form); fireEvent.submit(form);
  await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
  expect(screen.getByRole("button", { name: "Uploading…" })).toBeDisabled();
  reject(new Error("offline"));
  await screen.findByRole("alert");
  post.mockResolvedValue({ data: material } as never);
  get.mockImplementation(async url => {
    if (String(url).startsWith("/topics/t1/materials?")) return paged([material]);
    if (String(url) === "/topics/t1") return { data: topic } as never;
    return { data: discipline } as never;
  });
  fireEvent.submit(form);
  await screen.findByText("Lecture", { selector: "h3" });
  const firstOptions = post.mock.calls[0][2];
  expect(post.mock.calls[1][2]).toEqual(firstOptions);
  expect(post.mock.calls[0][1]).toBeInstanceOf(FormData);
});

it("keeps a deletion retry visible after the tombstone removes the row", async () => {
  const get = mockGet([material]);
  vi.spyOn(window, "confirm").mockReturnValue(true);
  const remove = vi.spyOn(api, "delete").mockRejectedValueOnce({ isAxiosError: true, response: {
    status: 503, data: { detail: { code: "MATERIAL_DELETE_PENDING" } },
  } }).mockResolvedValue({} as never);
  setup();
  await screen.findByText("Lecture", { selector: "h3" });
  get.mockImplementation(async url => {
    if (String(url).startsWith("/topics/t1/materials?")) return paged([]);
    if (String(url) === "/topics/t1") return { data: topic } as never;
    return { data: discipline } as never;
  });
  fireEvent.click(screen.getByRole("button", { name: "Delete material" }));
  await screen.findByText("Access is revoked, but the file is still in storage. Retry deletion.");
  await waitFor(() => expect(screen.queryByRole("heading", { name: "Lecture" })).not.toBeInTheDocument());
  fireEvent.click(screen.getByRole("button", { name: "Retry file deletion" }));
  await waitFor(() => expect(remove).toHaveBeenCalledTimes(2));
  expect(remove).toHaveBeenLastCalledWith("/materials/m1");
});

it("hides editing for archived content and rejects a topic under the wrong discipline URL", async () => {
  const get = mockGet();
  get.mockImplementation(async url => String(url) === "/topics/t1" ? { data: { ...topic, is_archived: true } } as never
    : String(url).includes("/materials?") ? paged([]) : { data: discipline } as never);
  const view = setup();
  await screen.findByText("The discipline or topic is archived. Materials can be downloaded. Restore it before editing.");
  expect(screen.queryByLabelText("Material file")).not.toBeInTheDocument();
  view.unmount();
  setup("/disciplines/d2/topics/t1");
  await screen.findByText("This topic does not belong to the specified discipline.");
  expect(screen.queryByLabelText("Material file")).not.toBeInTheDocument();
});

it.each([["ru", "Учебные материалы"], ["kk", "Оқу материалдары"], ["en", "Teaching materials"]] as const)(
  "localizes the new feature in %s", async (locale, label) => {
    await changeLocale(locale);
    mockGet();
    setup();
    expect(await screen.findByRole("heading", { name: label })).toBeVisible();
  },
);

it("isolates cached data by organization even for the same user and URL", async () => {
  const get = mockGet();
  const view = setup();
  await screen.findByRole("heading", { name: "React Hooks" });
  auth.user.organization_id = "org-b";
  get.mockRejectedValue({ isAxiosError: true, response: { status: 404, data: {} } });
  view.rerender(<QueryClientProvider client={view.client}><MemoryRouter initialEntries={["/disciplines/d1/topics/t1"]}>
    <Routes><Route path="/disciplines/:disciplineId/topics/:topicId" element={<TopicPage />} /></Routes>
  </MemoryRouter></QueryClientProvider>);
  await screen.findByRole("alert");
  expect(screen.queryByText("Use useState and useEffect")).not.toBeInTheDocument();
});
