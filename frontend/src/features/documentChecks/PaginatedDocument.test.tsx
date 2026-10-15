import { fireEvent, render, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { PaginatedDocument } from "./PaginatedDocument";
import type { DocumentCheckFinding, TeacherDocumentPreview } from "../../types/api";

vi.mock("./paginateDocx", () => ({ paginateDocx: async (root: HTMLElement) => {
  root.replaceChildren();
  return ["First half", "Second half"].map((content, i) => {
    const element = document.createElement("div");
    const body = document.createElement("div");
    const paragraph = document.createElement("p");
    paragraph.dataset.paragraphIndex = "2";
    paragraph.textContent = content;
    body.append(paragraph);
    const annotations = document.createElement("div");
    element.append(body, annotations);
    root.append(element);
    return { number: i + 1, section: 1, element, body, annotations };
  });
} }));

it("selects both HTML fragments by the original paragraph index without changing their formatting", async () => {
  const onParagraphSelect = vi.fn();
  const onPositions = vi.fn();
  const onSelect = vi.fn();
  const preview = { html: "", paragraph_count: 2, page_width_mm: 210, page_height_mm: 297,
    margin_top_mm: 20, margin_right_mm: 20, margin_bottom_mm: 20, margin_left_mm: 20 } satisfies TeacherDocumentPreview;
  const props = { preview, findings: [], selectedId: null, onSelect, onPositions, excludeFirstPage: false,
    paragraphSelectionEnabled: true, onParagraphSelect, paragraphTypes: { 2: "HEADING_1" as const } };
  const { container, rerender } = render(<PaginatedDocument {...props} />);
  await waitFor(() => expect(container.querySelectorAll('[data-paragraph-type="HEADING_1"]')).toHaveLength(2));
  const fragments = Array.from(container.querySelectorAll<HTMLElement>('[data-paragraph-index="2"]'));
  fireEvent.click(fragments[1]);
  expect(onParagraphSelect).toHaveBeenCalledWith({ index: 2, text: "First half Second half" });
  rerender(<PaginatedDocument {...props} selectedParagraphIndex={2} />);
  await waitFor(() => expect(container.querySelectorAll(".pf-docx-paragraph-selected")).toHaveLength(2));
  expect(fragments.every(node => node.style.textAlign === "")).toBe(true);
  expect(onSelect).not.toHaveBeenCalled();
});

it("highlights only the included fragment of a paragraph shared with an excluded page", async () => {
  const onPositions = vi.fn();
  const finding = { id: "indent", sequence: 1, severity: "ERROR", code: "PARAGRAPH_INDENT_MISMATCH",
    property_name: "left_indent", location: { paragraph_index: 2, pages: [2] } } as DocumentCheckFinding;
  const preview = { html: "", paragraph_count: 2, page_width_mm: 210, page_height_mm: 297,
    margin_top_mm: 20, margin_right_mm: 20, margin_bottom_mm: 20, margin_left_mm: 20 } satisfies TeacherDocumentPreview;
  const { container } = render(<PaginatedDocument preview={preview} findings={[finding]} selectedId={null}
    onSelect={vi.fn()} onPositions={onPositions} excludeFirstPage={false} excludedPages={[1]} />);
  await waitFor(() => expect(container.querySelectorAll(".pf-docx-error-location")).toHaveLength(1));
  expect(container.querySelector(".pf-docx-error-location")).toHaveTextContent("Second half");
  expect(onPositions).toHaveBeenLastCalledWith({ indent: { pages: [2], excerpt: "Second half" } });
});
