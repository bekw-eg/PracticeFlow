import { expect, test, type APIResponse } from "@playwright/test";
import { randomUUID } from "node:crypto";
import { execFileSync } from "node:child_process";

const apiBase = process.env.PLAYWRIGHT_API_BASE_URL
  ?? (process.env.PLAYWRIGHT_BASE_URL ? new URL("/api/v1", process.env.PLAYWRIGHT_BASE_URL).toString().replace(/\/$/, "") : "http://localhost:8000/api/v1");

async function body(response: APIResponse) {
  expect(response).toBeOK();
  return response.json();
}

function syntheticDocx() {
  return execFileSync(process.env.E2E_PYTHON ?? (process.platform === "win32" ? "python" : "python3"), ["-c", `
import io, sys, zipfile
w = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
paragraphs = ''.join('<w:p><w:pPr>' + ('<w:pageBreakBefore/>' if i == 3 else '') + '<w:spacing w:after="0" w:line="360"/><w:ind w:left="113" w:firstLine="709"/></w:pPr><w:r><w:rPr><w:rFonts w:ascii="Times New Roman"/><w:sz w:val="28"/></w:rPr><w:t>Synthetic ordinary body paragraph %s.</w:t></w:r></w:p>' % i for i in (2, 3))
entries = {
'[Content_Types].xml': '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
'_rels/.rels': '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
'word/document.xml': '<w:document xmlns:w="%s"><w:body><w:p><w:r><w:t>Synthetic cover</w:t><w:br w:type="page"/></w:r></w:p>' % w + paragraphs + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1134" w:right="850" w:bottom="1134" w:left="1701"/></w:sectPr></w:body></w:document>'}
output = io.BytesIO()
with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as package:
    for name, value in entries.items(): package.writestr(name, value)
sys.stdout.buffer.write(output.getvalue())
`]);
}

test("teacher excludes a preview page, reopens saved settings, and restores its checks", async ({ page, request }) => {
  test.setTimeout(90_000);
  const login = await body(await request.post(`${apiBase}/auth/login`, { data: {
    email: "teacher@demo.edu", password: "Practice123!", organization_slug: "demo-university",
  } }));
  const headers = { Authorization: `Bearer ${login.access_token}` };
  const profile = await body(await request.post(`${apiBase}/check-profiles`, { headers, data: { name: `Page exceptions ${randomUUID()}` } }));
  const version = await body(await request.post(`${apiBase}/check-profiles/${profile.id}/versions`, { headers, data: {} }));
  await body(await request.put(`${apiBase}/check-profiles/${profile.id}/versions/${version.id}/rules`, { headers, data: { rules: [{
    rule_type: "PARAGRAPH_SPACING_INDENTS", category: "formatting", severity: "ERROR", enabled: true,
    sort_order: 0, config_schema_version: 1, config: { line_spacing: 1.5, space_before_pt: 0,
      space_after_pt: 0, first_line_indent_mm: 12.5, left_indent_mm: 0, right_indent_mm: 0, alignment: null },
  }] } }));
  await body(await request.post(`${apiBase}/check-profiles/${profile.id}/versions/${version.id}/publish`, { headers }));
  const base = `${apiBase}/document-checks/teacher/submissions`;
  const uploaded = await body(await request.post(base, { headers: { ...headers, "Idempotency-Key": randomUUID() }, multipart: {
    profile_version_id: version.id,
    file: { name: "synthetic-page-exceptions.docx", mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document", buffer: syntheticDocx() },
  } }));
  const path = `${base}/${uploaded.id}`;
  // Fail at the API boundary if production object streams cannot be previewed.
  await body(await request.get(`${path}/preview`, { headers }));
  await body(await request.get(`${path}/paragraphs`, { headers }));
  await expect.poll(async () => (await body(await request.get(path, { headers }))).job.status, { timeout: 40_000 }).toBe("COMPLETED");
  const original = await body(await request.get(`${path}/findings`, { headers }));
  expect(original.map((finding: { location: { paragraph_index: number } }) => finding.location.paragraph_index)).toEqual([2, 3]);
  await page.goto("/login");
  await page.getByLabel("Email").fill("teacher@demo.edu");
  await page.getByLabel("Пароль").fill("Practice123!");
  await page.getByRole("button", { name: "Войти", exact: true }).click();
  await expect(page).toHaveURL(/\/document-checks$/);
  await page.goto(`/document-checks/${uploaded.id}`);
  await page.getByRole("tab", { name: "Правила", exact: true }).click();
  await page.getByRole("checkbox", { name: "Страница 2", exact: true }).check();
  const recheck = page.waitForResponse(response => response.url() === `${path}/recheck` && response.request().method() === "POST");
  await page.getByRole("button", { name: "Перепроверить", exact: true }).click();
  const run = await (await recheck).json();
  await expect.poll(async () => (await body(await request.get(`${path}/runs/${run.id}`, { headers }))).status, { timeout: 40_000 }).toBe("COMPLETED");
  const findings = await body(await request.get(`${path}/findings?job_id=${run.id}`, { headers }));
  expect(findings).toHaveLength(1);
  expect(findings[0].location).toMatchObject({ paragraph_index: 3, pages: [3] });
  await page.reload();
  await page.getByRole("tab", { name: "Правила", exact: true }).click();
  await expect(page.getByRole("checkbox", { name: "Страница 2", exact: true })).toBeChecked();
  await page.getByRole("button", { name: "Убрать все исключения", exact: true }).click();
  const restore = page.waitForResponse(response => response.url() === `${path}/recheck` && response.request().method() === "POST");
  await page.getByRole("button", { name: "Перепроверить", exact: true }).click();
  const restoredRun = await (await restore).json();
  await expect.poll(async () => (await body(await request.get(`${path}/runs/${restoredRun.id}`, { headers }))).status, { timeout: 40_000 }).toBe("COMPLETED");
  expect(await body(await request.get(`${path}/findings?job_id=${restoredRun.id}`, { headers }))).toHaveLength(2);
  expect(await body(await request.get(`${path}/findings?job_id=${uploaded.job.id}`, { headers }))).toEqual(original);
});
