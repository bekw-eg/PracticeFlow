import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { changeLocale } from "../../../i18n";
import type { DocumentMeta, DocumentModel, Section } from "../../../types/document";
import { DocumentPreview } from "../DocumentPreview";
import { PageSettingsPanel } from "../PageSettingsPanel";
import { SaveStatus } from "../SaveStatus";
import { SectionEditor } from "../SectionEditor";

const meta: DocumentMeta = {
  page_size: "A4",
  orientation: "portrait",
  margins: { top_mm: 20, bottom_mm: 20, left_mm: 30, right_mm: 10 },
  default_font: "Times New Roman",
  default_font_size: 14,
  line_spacing: 1.5,
  styles: { Normal: { alignment: "left" } },
  numbering: { enabled: true, start_number: 1, style: "decimal" },
};

const section: Section = {
  id: "section-authored",
  key: "introduction",
  // This is authored document content: the test asserts that translation only
  // affects the editor shell, never the section's text.
  title: "Авторский заголовок",
  level: 1,
  required: false,
  editable: true,
  page_break_before: false,
  numbering: { participates: true },
  blocks: [{ type: "paragraph", id: "paragraph-1", style_name: "Normal", style_override: null, runs: [{ kind: "text", id: "run-1", text: "Авторский текст", bold: false, italic: false, underline: false }] }],
};

const documentModel: DocumentModel = {
  schema_version: 1,
  meta,
  title_page: null,
  header: { enabled: false, blocks: [] },
  footer: { enabled: false, blocks: [] },
  sections: [section],
};

const localeCases = [
  {
    locale: "ru" as const,
    saved: "Сохранено",
    preview: "Предпросмотр документа формата A4",
    settings: "Параметры страницы документа",
    toolbar: "Панель инструментов редактора",
    bold: "Жирный",
  },
  {
    locale: "kk" as const,
    saved: "Сақталды",
    preview: "A4 құжатты алдын ала қарау",
    settings: "Құжат бетінің параметрлері",
    toolbar: "Редактордың құралдар тақтасы",
    bold: "Қалың",
  },
  {
    locale: "en" as const,
    saved: "Saved",
    preview: "A4 document preview",
    settings: "Document page settings",
    toolbar: "Editor toolbar",
    bold: "Bold",
  },
];

describe("editor i18n and accessibility", () => {
  afterEach(async () => {
    await changeLocale("ru");
  });

  it.each(localeCases)("localizes autosave, preview, page settings and toolbar in $locale", async ({ locale, saved, preview, settings, toolbar, bold }) => {
    await changeLocale(locale);

    const { unmount } = render(
      <>
        <SaveStatus state="saved" />
        <DocumentPreview document={documentModel} numbering={{}} />
        <PageSettingsPanel meta={meta} onChange={vi.fn()} />
      </>,
    );

    expect(screen.getByRole("status")).toHaveAttribute("aria-live", "polite");
    expect(screen.getByRole("status")).toHaveTextContent(saved);
    expect(screen.getByRole("region", { name: preview })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: settings })).toBeInTheDocument();
    unmount();

    await act(async () => {
      render(<SectionEditor section={section} numbering={{}} meta={meta} variableCatalog={[]} canEdit onBlocksChange={vi.fn()} />);
    });
    expect(screen.getByRole("toolbar", { name: toolbar })).toBeInTheDocument();
    expect(screen.getByTitle(bold)).toHaveAttribute("aria-label", bold);
    expect(screen.getByText("Авторский заголовок")).toBeInTheDocument();
  });
});
