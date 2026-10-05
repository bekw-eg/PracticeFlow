import { expect, test } from "@playwright/test";

test("Director password stage creates an MFA enrollment challenge without issuing a session", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("director@demo.edu");
  await page.getByLabel("Пароль").fill("Practice123!");
  const loginResponse = page.waitForResponse((response) => new URL(response.url()).pathname === "/api/v1/auth/login");
  await page.getByRole("button", { name: "Войти", exact: true }).click();

  const response = await loginResponse;
  expect(response.status()).toBe(202);
  const body = await response.json() as { status: string; access_token?: string };
  expect(body).toMatchObject({ status: "MFA_ENROLLMENT_REQUIRED" });
  expect(body.access_token).toBeUndefined();
  // Browser response headers deliberately hide Set-Cookie. Verify the actual
  // cookie jar instead of relying on an inaccessible header representation.
  const cookies = await page.context().cookies();
  expect(cookies.some((cookie) => cookie.name === "practiceflow_mfa_challenge")).toBe(true);
  expect(cookies.some((cookie) => cookie.name === "practiceflow_refresh")).toBe(false);

  await expect(page).toHaveURL(/\/mfa$/);
  await expect(page.getByRole("heading", { name: "Подключите приложение-аутентификатор" })).toBeVisible();
  await expect(page.getByRole("img", { name: "QR-код для добавления PracticeFlow в приложение-аутентификатор" })).toBeVisible();
  await expect(page.getByText("Если камера недоступна, введите ключ вручную:")).toBeVisible();
});
