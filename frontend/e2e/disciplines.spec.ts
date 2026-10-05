import { expect, test, type APIRequestContext } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";

const apiBase = process.env.PLAYWRIGHT_API_BASE_URL
  ?? (process.env.PLAYWRIGHT_BASE_URL ? new URL("/api/v1", process.env.PLAYWRIGHT_BASE_URL).toString().replace(/\/$/, "") : "http://localhost:8000/api/v1");

function officeFile(extension: "docx" | "pptx") {
  return execFileSync(process.env.E2E_PYTHON ?? (process.platform === "win32" ? "python" : "python3"), ["-c", `
import io, sys, zipfile
presentation = sys.argv[1] == "pptx"
main = "ppt/presentation.xml" if presentation else "word/document.xml"
mime = "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml" if presentation else "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
xml = '<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"/>' if presentation else '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Synthetic teaching material</w:t></w:r></w:p></w:body></w:document>'
stream = io.BytesIO()
with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
    archive.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/' + main + '" ContentType="' + mime + '"/></Types>')
    archive.writestr("_rels/.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="' + main + '"/></Relationships>')
    archive.writestr(main, xml)
sys.stdout.buffer.write(stream.getvalue())
`, extension]);
}

async function login(request: APIRequestContext, email: string, organizationSlug: string) {
  const response = await request.post(`${apiBase}/auth/login`, {
    data: { email, password: "Practice123!", organization_slug: organizationSlug },
  });
  expect(response).toBeOK();
  const body = await response.json() as { access_token: string };
  return { Authorization: `Bearer ${body.access_token}` };
}

test("teacher creates curriculum, uploads all formats, reloads and downloads; another tenant receives 404", async ({ page, request }) => {
  test.setTimeout(90_000);
  await page.goto("/login");
  await page.getByLabel("Email").fill("teacher@demo.edu");
  await page.getByLabel("Пароль").fill("Practice123!");
  await page.getByRole("button", { name: "Войти", exact: true }).click();
  await expect(page).toHaveURL(/\/document-checks$/);
  await page.getByRole("link", { name: "Дисциплины", exact: true }).click();
  const name = `Web Development ${randomUUID()}`;
  await page.getByLabel("Название дисциплины", { exact: true }).fill(name);
  await page.getByRole("button", { name: "Создать", exact: true }).click();
  await expect(page.getByRole("heading", { name, exact: true })).toBeVisible();
  const disciplineId = new URL(page.url()).pathname.split("/").at(-1)!;
  await page.getByLabel("Название темы", { exact: true }).fill("React Hooks");
  await page.getByLabel("Учебная цель", { exact: true }).fill("Научиться использовать useState и useEffect");
  await page.getByRole("button", { name: "Создать", exact: true }).click();
  await expect(page.getByRole("heading", { name: "React Hooks", exact: true })).toBeVisible();
  const topicId = new URL(page.url()).pathname.split("/").at(-1)!;
  const files = [
    { name: "lecture.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n") },
    { name: "methodical.docx", mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document", buffer: officeFile("docx") },
    { name: "hooks.pptx", mimeType: "application/vnd.openxmlformats-officedocument.presentationml.presentation", buffer: officeFile("pptx") },
  ];
  for (const file of files) {
    await page.getByLabel("Файл материала", { exact: true }).setInputFiles(file);
    await page.getByRole("button", { name: "Загрузить материал", exact: true }).click();
    await expect(page.getByRole("heading", { name: file.name, exact: true })).toBeVisible();
  }
  await page.reload();
  await expect(page.getByText("Научиться использовать useState и useEffect", { exact: true })).toBeVisible();
  for (const file of files) await expect(page.getByRole("heading", { name: file.name, exact: true })).toBeVisible();
  const downloadEvent = page.waitForEvent("download");
  await page.getByRole("listitem").filter({ has: page.getByRole("heading", { name: "lecture.pdf", exact: true }) })
    .getByRole("button", { name: "Скачать", exact: true }).click();
  const downloaded = await downloadEvent;
  expect(downloaded.suggestedFilename()).toBe("lecture.pdf");
  expect(await downloaded.failure()).toBeNull();

  const teacher = await login(request, "teacher@demo.edu", "demo-university");
  const materialsResponse = await request.get(`${apiBase}/topics/${topicId}/materials`, { headers: teacher });
  expect(materialsResponse).toBeOK();
  const materials = await materialsResponse.json() as { id: string; original_filename: string }[];
  expect(materials).toHaveLength(3);
  for (const material of materials) {
    const response = await request.get(`${apiBase}/materials/${material.id}/download`, { headers: teacher });
    expect(response).toBeOK();
    expect(await response.body()).toEqual(files.find(file => file.name === material.original_filename)!.buffer);
  }
  const other = await login(request, "teacher@other.demo.edu", "other-university");
  for (const path of [`/disciplines/${disciplineId}`, `/topics/${topicId}`, `/topics/${topicId}/materials`,
    `/materials/${materials[0].id}`, `/materials/${materials[0].id}/download`]) {
    expect((await request.get(apiBase + path, { headers: other })).status()).toBe(404);
  }
  const student = await login(request, "student1@demo.edu", "demo-university");
  expect((await request.post(apiBase + "/disciplines", { headers: student, data: { name: "Denied" } })).status()).toBe(403);
});
