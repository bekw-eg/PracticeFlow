import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { DocumentOutline } from "../DocumentOutline";
import type { DocumentModel } from "../../../types/document";

const document: DocumentModel = {
  schema_version: 1,
  meta: {
    page_size: "A4",
    orientation: "portrait",
    margins: { top_mm: 20, bottom_mm: 20, left_mm: 30, right_mm: 10 },
    default_font: "Times New Roman",
    default_font_size: 14,
    line_spacing: 1.5,
    styles: {},
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
      editable: false,
      page_break_before: false,
      numbering: { participates: true },
      blocks: [
        { type: "heading", id: "h_1", level: 2, style_name: null, runs: [{ kind: "text", id: "r_1", text: "Цель работы", bold: false, italic: false, underline: false }], numbering: { participates: true } },
      ],
    },
    {
      id: "sec_2",
      key: "ch1",
      title: "Глава 1",
      level: 1,
      required: true,
      editable: true,
      page_break_before: true,
      numbering: { participates: true },
      blocks: [],
    },
  ],
};

describe("DocumentOutline", () => {
  it("renders sections and nested headings with server-provided numbers", () => {
    const numbering = { sec_1: "1", h_1: "1.1", sec_2: "2" };
    render(<DocumentOutline document={document} numbering={numbering} />);

    expect(screen.getByText("Введение")).toBeInTheDocument();
    expect(screen.getByText("Глава 1")).toBeInTheDocument();
    expect(screen.getByText("Цель работы")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("1.1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "2Глава 1" })).toBeInTheDocument();
  });

  it("renders without numbers when numbering is empty (e.g. before first load)", () => {
    render(<DocumentOutline document={document} numbering={{}} />);
    expect(screen.getByText("Введение")).toBeInTheDocument();
  });
});
