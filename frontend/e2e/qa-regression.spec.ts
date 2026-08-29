import { expect, test } from "@playwright/test";

test("student can open a revision-required report without requesting teacher-only variables", async ({ page }) => {
  const teacherOnlyResponses: number[] = [];
  const consoleErrors: string[] = [];

  page.on("response", (response) => {
    if (new URL(response.url()).pathname === "/api/v1/variables/catalog") teacherOnlyResponses.push(response.status());
  });
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });

  await page.goto("/login");
  await page.getByLabel("Email").fill("student1@demo.edu");
  await page.getByLabel("Пароль").fill("Practice123!");
  await page.getByRole("button", { name: "Войти" }).click();

  await expect(page).toHaveURL(/\/reports$/);
  // A fresh anonymous context can emit expected refresh-token 401s while the
  // auth provider initializes. The regression boundary starts after student
  // authentication succeeds and covers opening the report editor.
  consoleErrors.length = 0;
  await page.getByRole("link", { name: "Редактировать" }).click();

  await expect(page.getByRole("heading", { name: "Отчёт по практике" })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Редактор раздела: Введение" })).toBeVisible();
  await expect(page.getByText("This action requires one of: ['TEACHER'].")).toHaveCount(0);

  const editorLabels = await page.locator('[contenteditable="true"][aria-label^="Редактор раздела:"]').evaluateAll((editors) =>
    editors.map((editor) => editor.getAttribute("aria-label") ?? "")
  );
  expect(editorLabels.length).toBeGreaterThan(0);
  expect(new Set(editorLabels).size).toBe(editorLabels.length);
  expect(teacherOnlyResponses).toEqual([]);
  expect(consoleErrors).toEqual([]);
});

test("login shell exposes metadata and real non-indexable crawl-control assets", async ({ page, request }) => {
  await page.goto("/login");

  await expect(page.locator('meta[name="description"]')).toHaveAttribute("content", /PracticeFlow/);
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", "noindex, nofollow");
  await expect(page.locator('meta[property="og:title"]')).toHaveAttribute("content", "PracticeFlow");
  await expect(page.locator('meta[property="og:description"]')).toHaveAttribute("content", /Платформа управления/);
  await expect(page.locator('meta[property="og:type"]')).toHaveAttribute("content", "website");
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute("href", "/login");

  const [robots, sitemap] = await Promise.all([request.get("/robots.txt"), request.get("/sitemap.xml")]);
  expect(robots.headers()["content-type"]).toContain("text/plain");
  expect(await robots.text()).toContain("Disallow: /");

  expect(sitemap.headers()["content-type"]).toContain("xml");
  const sitemapBody = await sitemap.text();
  expect(sitemapBody).toContain("<urlset");
  expect(sitemapBody).not.toContain("<!doctype html>");
  expect(sitemapBody).not.toMatch(/\/(admin|groups|reports|templates|profile)/);
});
