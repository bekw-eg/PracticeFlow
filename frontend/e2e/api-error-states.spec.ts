import { expect, test } from "@playwright/test";

const reportsRequest = /\/api\/v1\/reports\?offset=0&limit=25$/;

test("student reports replaces a 404 response with an accessible error and can retry", async ({ page }) => {
  await page.route(reportsRequest, async (route) => {
    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Report list is unavailable" }),
    });
  });

  await page.goto("/login");
  await page.getByLabel("Email").fill("student1@demo.edu");
  await page.getByLabel("Пароль").fill("Practice123!");
  await page.getByRole("button", { name: "Войти" }).click();

  await expect(page).toHaveURL(/\/reports$/);
  const error = page.getByRole("alert");
  await expect(error).toContainText("Данные не найдены");
  await expect(page.getByText("Загрузка отчётов…")).toHaveCount(0);

  await page.unroute(reportsRequest);
  await page.getByRole("button", { name: "Повторить" }).click();

  await expect(error).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Редактировать" })).toBeVisible();
});
