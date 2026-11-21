import { expect, test } from "@playwright/test";

test("teacher can navigate between document checks and groups without console errors", async ({ page }) => {
  const consoleErrors: string[] = [];

  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });

  await page.goto("/login");
  await page.getByLabel("Email").fill("teacher@demo.edu");
  await page.getByLabel("Пароль").fill("Practice123!");
  await page.getByRole("button", { name: "Войти", exact: true }).click();

  await expect(page).toHaveURL(/\/document-checks$/);
  consoleErrors.length = 0;

  await page.getByRole("link", { name: "Мои группы", exact: true }).click();
  await expect(page).toHaveURL(/\/groups$/);
  await expect(page.getByText("E2E-Group")).toBeVisible();
  await page.getByRole("link", { name: /E2E-Group/ }).click();
  await expect(page).toHaveURL(/\/groups\/[0-9a-f-]+$/);
  await expect(page.getByText("Состав группы")).toBeVisible();

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
