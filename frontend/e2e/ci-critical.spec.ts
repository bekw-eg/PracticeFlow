import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const E2E_PASSWORD = "Practice123!";
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
  await page.getByRole("button", { name: "Войти", exact: true }).click();
}

async function loginThroughApi(request: APIRequestContext, email: string, organizationSlug = "demo-university") {
  const response = await request.post(apiPath("/auth/login"), {
    data: { email, password: E2E_PASSWORD, organization_slug: organizationSlug },
  });
  expect(response).toBeOK();
  const body = (await response.json()) as { access_token: string };
  return { Authorization: `Bearer ${body.access_token}` };
}

test("anonymous requests receive 401 and student login lands on the unavailable workspace notice", async ({ page, request }) => {
  const anonymousGroups = await request.get(apiPath("/groups"));
  expect(anonymousGroups.status()).toBe(401);

  await page.goto("/groups");
  await expect(page).toHaveURL(/\/login$/);

  await loginThroughUi(page, "student1@demo.edu");
  await expect(page).toHaveURL(/\/student-unavailable$/);
  await expect(page.getByRole("heading", { name: "Веб-кабинет предназначен для преподавателей и администрации" })).toBeVisible();
});

test("student role is denied teacher data and another tenant resource returns 404", async ({ request }) => {
  const studentHeaders = await loginThroughApi(request, "student1@demo.edu");
  const teacherOnly = await request.get(apiPath("/groups/00000000-0000-0000-0000-000000000001/available-students"), { headers: studentHeaders });
  expect(teacherOnly.status()).toBe(403);
  expect(await teacherOnly.json()).toMatchObject({ detail: "This action requires one of: ['TEACHER']." });

  const otherTeacherHeaders = await loginThroughApi(request, "teacher@other.demo.edu", "other-university");
  const createdProfile = await request.post(apiPath("/check-profiles"), {
    headers: otherTeacherHeaders,
    data: { name: "Other Tenant Check Profile" },
  });
  expect(createdProfile.status()).toBe(201);
  const { id: otherProfileId } = (await createdProfile.json()) as { id: string };

  const teacherHeaders = await loginThroughApi(request, "teacher@demo.edu");
  const crossTenantProfile = await request.get(apiPath(`/check-profiles/${otherProfileId}`), { headers: teacherHeaders });
  expect(crossTenantProfile.status()).toBe(404);
});

test("teacher login lands on document checks and admin-only route is blocked in the UI", async ({ page }) => {
  await loginThroughUi(page, "teacher@demo.edu");
  await expect(page).toHaveURL(/\/document-checks$/);
  await expect(page.getByRole("heading", { name: "Проверка документов" })).toBeVisible();

  await page.goto("/admin");
  await expect(page).toHaveURL(/\/document-checks$/);
});

test("legacy report and template API routes are removed", async ({ request }) => {
  const headers = await loginThroughApi(request, "teacher@demo.edu");
  for (const path of ["/templates", "/reports", "/variables/catalog"]) {
    expect((await request.get(apiPath(path), { headers })).status()).toBe(404);
  }
});
