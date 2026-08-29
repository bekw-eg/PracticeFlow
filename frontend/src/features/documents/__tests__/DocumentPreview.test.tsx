import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DocumentPreview } from "../DocumentPreview";
import type { DocumentModel } from "../../../types/document";

const longText = "Связный абзац должен переноситься браузером как единый текст. ".repeat(60);

const document: DocumentModel = {
  schema_version: 1,
  meta: {
    page_size: "A4",
    orientation: "portrait",
    margins: { top_mm: 20, bottom_mm: 20, left_mm: 30, right_mm: 10 },
    default_font: "Times New Roman",
    default_font_size: 14,
    line_spacing: 1.5,
    styles: { Normal: { alignment: "left", line_spacing: 1.5, first_line_indent_mm: 12.5 } },
    numbering: { enabled: true, start_number: 1, style: "decimal" },
  },
  title_page: null,
  header: { enabled: false, blocks: [] },
  footer: { enabled: false, blocks: [] },
  sections: [
    {
      id: "sec_1",
      key: "intro",
      title: "Введение",
      level: 1,
      required: true,
      editable: true,
      page_break_before: false,
      numbering: { participates: true },
      blocks: [
        {
          type: "paragraph",
          id: "p_1",
          style_name: "Normal",
          style_override: { left_indent_mm: 5, space_after_pt: 8 },
          runs: [
            { kind: "text", id: "r_1", text: longText, bold: false, italic: false, underline: false },
            { kind: "text", id: "r_2", text: "Выделенный фрагмент.", bold: true, italic: false, underline: false },
          ],
        },
      ],
    },
  ],
};

describe("DocumentPreview", () => {
  it("keeps a long Tiptap paragraph as one semantic paragraph with inline text", () => {
    const { container } = render(<DocumentPreview document={document} numbering={{ sec_1: "1" }} />);
    const paragraph = container.querySelector("p");

    expect(paragraph).not.toBeNull();
    expect(paragraph?.textContent).toBe(`${longText}Выделенный фрагмент.`);
    expect(paragraph?.querySelector("div")).toBeNull();
    expect(paragraph?.querySelector("strong")?.textContent).toBe("Выделенный фрагмент.");
    expect(paragraph?.style.textAlign).toBe("left");
    expect(paragraph?.style.textIndent).toBe("12.5mm");
    expect(paragraph?.style.marginLeft).toBe("5mm");
    expect(paragraph?.style.wordSpacing).toBe("");
    expect(paragraph?.style.letterSpacing).toBe("");
    expect(paragraph?.style.whiteSpace).toBe("");
  });

  it("uses page-sized browser columns so overflowing text continues on a new A4 page", () => {
    const { container } = render(<DocumentPreview document={document} numbering={{ sec_1: "1" }} />);
    const flow = container.querySelector('[style*="column-width"]') as HTMLElement;

    expect(flow).toBeTruthy();
    expect(flow.style.columnWidth).toBe("170mm");
    expect(flow.style.height).toBe("297mm");
    expect(flow.style.columnFill).toBe("auto");
  });
});
