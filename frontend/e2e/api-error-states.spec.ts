import { expect, test } from "@playwright/test";

const groupsRequest = /\/api\/v1\/groups\?offset=0&limit=25$/;

test("teacher groups replaces a 404 response with an accessible error and can retry", async ({ page }) => {
  await page.route(groupsRequest, async (route) => {
    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Group list is unavailable" }),
    });
  });

  await page.goto("/login");
  await page.getByLabel("Email").fill("teacher@demo.edu");
  await page.getByLabel("Пароль").fill("Practice123!");
  await page.getByRole("button", { name: "Войти", exact: true }).click();

  await expect(page).toHaveURL(/\/document-checks$/);
  await page.getByRole("link", { name: "Мои группы", exact: true }).click();
  await expect(page).toHaveURL(/\/groups$/);

  const error = page.getByRole("alert");
  await expect(error).toContainText("Данные не найдены");
  await expect(page.getByText("Загрузка групп…")).toHaveCount(0);

  await page.unroute(groupsRequest);
  await page.getByRole("button", { name: "Повторить" }).click();

  await expect(error).toHaveCount(0);
  await expect(page.getByText("E2E-Group")).toBeVisible();
});
