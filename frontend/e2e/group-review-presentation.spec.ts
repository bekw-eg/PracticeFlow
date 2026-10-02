import { expect, test, type APIRequestContext, type APIResponse } from "@playwright/test";
import { randomUUID } from "node:crypto";
import { execFileSync } from "node:child_process";

const apiBase = process.env.PLAYWRIGHT_API_BASE_URL
  ?? (process.env.PLAYWRIGHT_BASE_URL ? new URL("/api/v1", process.env.PLAYWRIGHT_BASE_URL).toString().replace(/\/$/, "") : "http://localhost:8000/api/v1");

// Synthetic DOCX constructed in memory with Python's standard library.
// CI already provides Python; no student file or fixture credentials are read.
function syntheticDocx() {
  return execFileSync(process.env.E2E_PYTHON ?? (process.platform === "win32" ? "python" : "python3"), ["-c", `
import io, sys, zipfile
entries = {
"[Content_Types].xml": '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
"_rels/.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
"word/document.xml": '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Synthetic title page</w:t><w:br w:type="page"/></w:r></w:p><w:p><w:r><w:t>SYNTHETIC_PRIVATE_MARKER</w:t></w:r></w:p><w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="567" w:right="850" w:bottom="1134" w:left="1701"/></w:sectPr></w:body></w:document>'}
output = io.BytesIO()
with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as package:
    for name, value in entries.items(): package.writestr(name, value)
sys.stdout.buffer.write(output.getvalue())
`]);
}

async function body(response: APIResponse) {
  expect(response).toBeOK();
  return response.json();
}

test("teacher previews a partial group snapshot and repeatedly downloads its private PPTX", async ({ page, request }) => {
  test.setTimeout(90_000);
  const login = await body(await request.post(`${apiBase}/auth/login`, { data: {
    email: "teacher@demo.edu", password: "Practice123!", organization_slug: "demo-university",
  } }));
  const headers = { Authorization: `Bearer ${login.access_token}` };
  const base = `${apiBase}/document-checks/teacher`;
  const profile = await body(await request.post(`${apiBase}/check-profiles`, { headers, data: { name: `PPTX E2E ${randomUUID()}` } }));
  const version = await body(await request.post(`${apiBase}/check-profiles/${profile.id}/versions`, { headers, data: {} }));
  await body(await request.put(`${apiBase}/check-profiles/${profile.id}/versions/${version.id}/rules`, { headers, data: { rules: [{
    rule_type: "PAGE_FORMAT_MARGINS", category: "formatting", severity: "ERROR", enabled: true,
    sort_order: 0, config_schema_version: 1, config: { page_size: "A4", orientation: "PORTRAIT",
      margins: { top_mm: 20, right_mm: 15, bottom_mm: 20, left_mm: 30 }, width_mm: null, height_mm: null },
  }] } }));
  await body(await request.post(`${apiBase}/check-profiles/${profile.id}/versions/${version.id}/publish`, { headers }));
  const group = await body(await request.post(`${base}/groups`, { headers, data: { name: "БК 2405" } }));
  const bytes = syntheticDocx();
  async function upload(client: APIRequestContext) {
    return body(await client.post(`${base}/submissions`, { headers: { ...headers, "Idempotency-Key": randomUUID() }, multipart: {
      profile_version_id: version.id, review_group_id: group.id, student_label: "SYNTHETIC_PRIVATE_MARKER",
      work_title: "SYNTHETIC_PRIVATE_MARKER", work_type: "REPORT",
      file: { name: "SYNTHETIC_PRIVATE_MARKER.docx", mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document", buffer: bytes },
    } }));
  }
  const first = await upload(request);
  await upload(request);
  await expect.poll(async () => (await body(await request.get(`${base}/submissions/${first.id}`, { headers }))).job.status,
    { timeout: 40_000 }).toBe("COMPLETED");
  await body(await request.post(`${base}/submissions/${first.id}/review/complete`, { headers, data: {
    revision: 0, job_id: first.job.id, remarks: "SYNTHETIC_PRIVATE_MARKER individual remark",
  } }));
  await page.goto("/login");
  await page.getByLabel("Email").fill("teacher@demo.edu");
  await page.getByLabel("Пароль").fill("Practice123!");
  await page.getByRole("button", { name: "Войти", exact: true }).click();
  await expect(page).toHaveURL(/\/document-checks$/);
  await page.goto(`/review-groups/${group.id}`);
  await page.getByRole("button", { name: "Сформировать презентацию отчёта о проверке", exact: true }).click();
  await expect(page.getByText("Проверена только часть группы: 1 из 2. В статистику включено: 1.")).toBeVisible();
  await page.getByLabel("Выводы преподавателя", { exact: true }).fill("Обсудить требования к полям на занятии.");
  await page.getByRole("checkbox", { name: "Пример 1", exact: true }).check();
  await page.getByRole("button", { name: "Предпросмотр содержания", exact: true }).click();
  const preview = page.getByRole("article", { name: "Предпросмотр содержания" });
  await expect(preview.getByText("Обсудить требования к полям на занятии.")).toBeVisible();
  await expect(preview).not.toContainText("SYNTHETIC_PRIVATE_MARKER");
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Сформировать и скачать PPTX", exact: true }).click();
  expect((await download).suggestedFilename()).toMatch(/\.pptx$/);
  const reports = await body(await request.get(`${base}/groups/${group.id}/reports`, { headers }));
  expect(reports).toHaveLength(1);
  const path = `${base}/groups/${group.id}/reports/${reports[0].id}`;
  const saved = await body(await request.get(path, { headers }));
  expect(saved.snapshot.summary).toMatchObject({ total_works: 2, reviewed_works: 1, included_works: 1, pending_works: 1 });
  expect(saved.content.remarks).toEqual([]);
  expect(saved.content.examples).toHaveLength(1);
  expect(JSON.stringify(saved.content.examples)).not.toContain("SYNTHETIC_PRIVATE_MARKER");
  const file = await request.get(`${path}/download`, { headers });
  expect(file).toBeOK();
  expect(file.headers()["cache-control"]).toBe("private, no-store");
  const originalBytes = await file.body();
  expect(originalBytes.subarray(0, 2).toString()).toBe("PK");
  await body(await request.put(`${base}/groups/${group.id}`, { headers, data: { name: "Changed after report" } }));
  const settings = await body(await request.get(`${base}/submissions/${first.id}/settings`, { headers }));
  await body(await request.post(`${base}/submissions/${first.id}/recheck`, {
    headers: { ...headers, "Idempotency-Key": randomUUID() }, data: { revision: settings.revision },
  }));
  expect(await (await request.get(`${path}/download`, { headers })).body()).toEqual(originalBytes);
  expect(await body(await request.get(path, { headers }))).toEqual(saved);
  expect((await request.get(`${path}/download`)).status()).toBe(401);
});
