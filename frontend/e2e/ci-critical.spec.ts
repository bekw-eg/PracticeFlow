import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const E2E_PASSWORD = "Practice123!";
const OTHER_TENANT_REPORT_ID = "d4ccf32d-6f2b-4f0e-9cbd-3bd1b2c3c502";
// CI exercises the production Nginx proxy on one origin. Local Docker
// development uses Vite on :5173 and the API directly on :8000, so the API
// request fixture needs an explicit base instead of assuming a proxy exists.
const apiBaseUrl = process.env.PLAYWRIGHT_API_BASE_URL
  ?? (process.env.PLAYWRIGHT_BASE_URL ? new URL("/api/v1", process.env.PLAYWRIGHT_BASE_URL).toString().replace(/\/$/, "") : "http://localhost:8000/api/v1");

function apiPath(path: string) {
  return `${apiBaseUrl}${path}`;
}

async function loginThroughUi(page: Page, email: string) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Пароль").fill(E2E_PASSWORD);
  await page.getByRole("button", { name: "Войти" }).click();
}

async function loginThroughApi(request: APIRequestContext, email: string, organizationSlug = "demo-university") {
  const response = await request.post(apiPath("/auth/login"), {
    data: { email, password: E2E_PASSWORD, organization_slug: organizationSlug },
  });
  expect(response).toBeOK();
  const body = (await response.json()) as { access_token: string };
  return { Authorization: `Bearer ${body.access_token}` };
}

const TINY_PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBgAAAABQABpfZFQAAAAABJRU5ErkJggg==",
  "base64",
);

test("anonymous requests receive 401 and student login opens the revision-required report", async ({ page, request }) => {
  const anonymousReports = await request.get(apiPath("/reports"));
  expect(anonymousReports.status()).toBe(401);

  await page.goto("/reports");
  await expect(page).toHaveURL(/\/login$/);

  await loginThroughUi(page, "student1@demo.edu");
  await expect(page).toHaveURL(/\/reports$/);
  await expect(page.getByRole("heading", { name: "Мои отчёты" })).toBeVisible();
  await page.getByRole("link", { name: "Редактировать" }).click();
  await expect(page.getByRole("heading", { name: "Отчёт по практике" })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Редактор раздела: Введение" })).toBeVisible();
});

test("student role is denied teacher data and cannot discover another tenant report", async ({ request }) => {
  const headers = await loginThroughApi(request, "student1@demo.edu");

  const teacherOnly = await request.get(apiPath("/groups/00000000-0000-0000-0000-000000000001/available-students"), { headers });
  expect(teacherOnly.status()).toBe(403);
  expect(await teacherOnly.json()).toMatchObject({ detail: "This action requires one of: ['TEACHER']." });

  const crossTenantReport = await request.get(apiPath(`/reports/${OTHER_TENANT_REPORT_ID}`), { headers });
  // The tenant-scoped repository deliberately turns a foreign report into a
  // 404, rather than exposing that another tenant owns this resource.
  expect(crossTenantReport.status()).toBe(404);
  expect(await crossTenantReport.json()).toMatchObject({ detail: "Report not found" });
});

test("teacher login lands on groups and the student-only route is blocked in the UI", async ({ page }) => {
  await loginThroughUi(page, "teacher@demo.edu");
  await expect(page).toHaveURL(/\/groups$/);
  await expect(page.getByRole("heading", { name: "Мои группы" })).toBeVisible();

  await page.goto("/reports");
  await expect(page).toHaveURL(/\/groups$/);
});

test("student asynchronous DOCX export is deduplicated, completed by the worker and downloaded", async ({ request }) => {
  const headers = await loginThroughApi(request, "student1@demo.edu");
  const reports = await request.get(apiPath("/reports"), { headers });
  expect(reports).toBeOK();
  const reportId = (await reports.json())[0].id as string;

  const first = await request.post(apiPath(`/reports/${reportId}/exports/docx`), { headers });
  expect(first.status()).toBe(202);
  const firstBody = await first.json() as { job_id: string; status: string };
  expect(firstBody.status).toBe("queued");
  const duplicate = await request.post(apiPath(`/reports/${reportId}/exports/docx`), { headers });
  expect(duplicate.status()).toBe(202);
  expect((await duplicate.json()) as { job_id: string }).toMatchObject({ job_id: firstBody.job_id });

  await expect.poll(async () => {
    const state = await request.get(apiPath(`/export-jobs/${firstBody.job_id}`), { headers });
    expect(state).toBeOK();
    return ((await state.json()) as { status: string }).status;
  }, { timeout: 30_000, intervals: [250, 500, 1_000] }).toBe("succeeded");

  const download = await request.get(apiPath(`/export-jobs/${firstBody.job_id}/download`), { headers });
  expect(download).toBeOK();
  expect(download.headers()["content-type"]).toContain("application/vnd.openxmlformats-officedocument.wordprocessingml.document");
  expect((await download.body()).byteLength).toBeGreaterThan(0);
});

test("private MinIO image storage remains tenant-scoped behind the authorized API", async ({ request }) => {
  const ownerHeaders = await loginThroughApi(request, "student1@demo.edu");
  const upload = await request.post(apiPath("/files"), {
    headers: ownerHeaders,
    multipart: {
      file: {
        name: "untrusted-name.png",
        mimeType: "image/png",
        buffer: TINY_PNG,
      },
    },
  });
  expect(upload.status()).toBe(201);
  const uploaded = (await upload.json()) as { id: string; url: string };
  expect(uploaded.url).toBe(`/api/v1/files/${uploaded.id}`);

  const ownerDownload = await request.get(apiPath(`/files/${uploaded.id}`), { headers: ownerHeaders });
  expect(ownerDownload).toBeOK();
  expect(await ownerDownload.body()).toEqual(TINY_PNG);

  const otherTenantHeaders = await loginThroughApi(request, "student@other.demo.edu", "other-university");
  const otherTenantDownload = await request.get(apiPath(`/files/${uploaded.id}`), { headers: otherTenantHeaders });
  expect(otherTenantDownload.status()).toBe(404);
});
