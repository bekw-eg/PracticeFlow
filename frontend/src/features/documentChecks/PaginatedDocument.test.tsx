import { fireEvent, render, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { PaginatedDocument } from "./PaginatedDocument";
import type { TeacherDocumentPreview } from "../../types/api";

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
