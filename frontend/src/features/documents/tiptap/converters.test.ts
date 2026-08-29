import { describe, expect, it } from "vitest";
import { blockToTiptapNode, blocksToTiptapDoc, tiptapDocToBlocks, tiptapNodeToBlock } from "./converters";
import type { Block, HeadingBlock, ImageBlock, PageBreakBlock, ParagraphBlock, TableBlock, ListBlock, VariableCatalogEntry } from "../../../types/document";

const catalog: VariableCatalogEntry[] = [
  { key: "student.full_name", label: "ФИО студента" },
  { key: "academic_year", label: "Учебный год" },
];

function roundTrip(block: Block): Block {
  const tiptapNode = blockToTiptapNode(block, catalog);
  return tiptapNodeToBlock(tiptapNode);
}

describe("paragraph round-trip", () => {
  it("preserves plain text", () => {
    const block: ParagraphBlock = {
      type: "paragraph",
      id: "p_1",
      style_name: "Normal",
      style_override: null,
      runs: [{ kind: "text", id: "r_1", text: "Привет, мир", bold: false, italic: false, underline: false }],
    };
    const result = roundTrip(block) as ParagraphBlock;
    expect(result.type).toBe("paragraph");
    expect(result.id).toBe("p_1");
    expect(result.style_name).toBe("Normal");
    expect(result.runs).toHaveLength(1);
    expect(result.runs[0]).toMatchObject({ kind: "text", text: "Привет, мир" });
  });

  it("preserves bold/italic/underline marks independently", () => {
    const block: ParagraphBlock = {
      type: "paragraph",
      id: "p_1",
      style_name: "Normal",
      style_override: null,
      runs: [
        { kind: "text", id: "r_1", text: "bold", bold: true, italic: false, underline: false },
        { kind: "text", id: "r_2", text: "italic", bold: false, italic: true, underline: false },
        { kind: "text", id: "r_3", text: "underline", bold: false, italic: false, underline: true },
        { kind: "text", id: "r_4", text: "all three", bold: true, italic: true, underline: true },
      ],
    };
    const result = roundTrip(block) as ParagraphBlock;
    expect(result.runs).toHaveLength(4);
    expect(result.runs[0]).toMatchObject({ text: "bold", bold: true, italic: false, underline: false });
    expect(result.runs[1]).toMatchObject({ text: "italic", bold: false, italic: true, underline: false });
    expect(result.runs[2]).toMatchObject({ text: "underline", bold: false, italic: false, underline: true });
    expect(result.runs[3]).toMatchObject({ text: "all three", bold: true, italic: true, underline: true });
  });

  it("preserves the complete paragraph override needed by preview and export", () => {
    const block: ParagraphBlock = {
      type: "paragraph",
      id: "p_1",
      style_name: "Normal",
      style_override: { alignment: "center", line_spacing: 1.15, first_line_indent_mm: 8, left_indent_mm: 4, bold: true },
      runs: [{ kind: "text", id: "r_1", text: "centered", bold: false, italic: false, underline: false }],
    };
    const result = roundTrip(block) as ParagraphBlock;
    expect(result.style_override).toEqual(block.style_override);
  });

  it("preserves a variable run and its key (not just its display label)", () => {
    const block: ParagraphBlock = {
      type: "paragraph",
      id: "p_1",
      style_name: "Normal",
      style_override: null,
      runs: [
        { kind: "text", id: "r_1", text: "Студент: ", bold: false, italic: false, underline: false },
        { kind: "variable", id: "v_1", key: "student.full_name", resolved_text: null },
      ],
    };
    const result = roundTrip(block) as ParagraphBlock;
    expect(result.runs).toHaveLength(2);
    expect(result.runs[1]).toMatchObject({ kind: "variable", key: "student.full_name" });
    // resolved_text must never be persisted through the editor round-trip —
    // it's a read-time-only field populated by the backend resolver.
    expect((result.runs[1] as { resolved_text: string | null }).resolved_text).toBeNull();
  });

  it("preserves an empty paragraph without inventing content", () => {
    const block: ParagraphBlock = { type: "paragraph", id: "p_1", style_name: "Normal", style_override: null, runs: [] };
    const result = roundTrip(block) as ParagraphBlock;
    expect(result.runs.every((r) => r.kind !== "text" || r.text === "")).toBe(true);
  });
});

describe("heading round-trip", () => {
  it("preserves level and numbering participation, never a visual-only size", () => {
    const block: HeadingBlock = {
      type: "heading",
      id: "h_1",
      level: 2,
      style_name: "Heading2",
      runs: [{ kind: "text", id: "r_1", text: "Глава", bold: false, italic: false, underline: false }],
      numbering: { participates: false },
    };
    const result = roundTrip(block) as HeadingBlock;
    expect(result.type).toBe("heading");
    expect(result.level).toBe(2);
    expect(result.style_name).toBe("Heading2");
    expect(result.numbering.participates).toBe(false);
  });
});

describe("table round-trip", () => {
  it("preserves row/cell structure and nested paragraph content", () => {
    const block: TableBlock = {
      type: "table",
      id: "tbl_1",
      rows: [
        {
          id: "row_1",
          cells: [
            { id: "cell_1", blocks: [{ type: "paragraph", id: "p_1", style_name: "Normal", style_override: null, runs: [{ kind: "text", id: "r_1", text: "A1", bold: false, italic: false, underline: false }] }] },
            { id: "cell_2", blocks: [{ type: "paragraph", id: "p_2", style_name: "Normal", style_override: null, runs: [{ kind: "text", id: "r_2", text: "B1", bold: false, italic: false, underline: false }] }] },
          ],
        },
      ],
    };
    const result = roundTrip(block) as TableBlock;
    expect(result.type).toBe("table");
    expect(result.rows).toHaveLength(1);
    expect(result.rows[0].cells).toHaveLength(2);
    const firstCellParagraph = result.rows[0].cells[0].blocks[0] as ParagraphBlock;
    expect(firstCellParagraph.runs[0]).toMatchObject({ text: "A1" });
  });
});

describe("image round-trip", () => {
  it("preserves file reference, dimensions, alignment, and caption", () => {
    const block: ImageBlock = { type: "image", id: "img_1", file_id: "file_abc", width_mm: 80, alignment: "right", caption: "Рисунок 1" };
    const result = roundTrip(block) as ImageBlock;
    expect(result).toMatchObject({ type: "image", file_id: "file_abc", width_mm: 80, alignment: "right", caption: "Рисунок 1" });
  });
});

describe("page break round-trip", () => {
  it("survives as a distinct block, not merged into surrounding paragraphs", () => {
    const block: PageBreakBlock = { type: "pageBreak", id: "brk_1" };
    const result = roundTrip(block);
    expect(result.type).toBe("pageBreak");
  });
});

describe("list round-trip", () => {
  it("preserves ordered flag and item content", () => {
    const block: ListBlock = {
      type: "list",
      id: "list_1",
      ordered: true,
      items: [{ id: "li_1", blocks: [{ type: "paragraph", id: "p_1", style_name: "Normal", style_override: null, runs: [{ kind: "text", id: "r_1", text: "Пункт 1", bold: false, italic: false, underline: false }] }] }],
    };
    const result = roundTrip(block) as ListBlock;
    expect(result.ordered).toBe(true);
    expect(result.items).toHaveLength(1);
  });
});

describe("full document round-trip", () => {
  it("preserves an entire section's mixed block content through doc-level conversion", () => {
    const blocks: Block[] = [
      { type: "heading", id: "h_1", level: 1, style_name: null, runs: [{ kind: "text", id: "r_1", text: "Введение", bold: false, italic: false, underline: false }], numbering: { participates: true } },
      { type: "paragraph", id: "p_1", style_name: "Normal", style_override: null, runs: [{ kind: "text", id: "r_2", text: "Текст", bold: true, italic: false, underline: false }] },
      { type: "pageBreak", id: "brk_1" },
      { type: "image", id: "img_1", file_id: "f_1", width_mm: 100, alignment: "center", caption: "" },
    ];
    const doc = blocksToTiptapDoc(blocks, catalog);
    const result = tiptapDocToBlocks(doc);
    expect(result.map((b) => b.type)).toEqual(["heading", "paragraph", "pageBreak", "image"]);
    expect(result[0].id).toBe("h_1");
    expect(result[1].id).toBe("p_1");
    expect((result[1] as ParagraphBlock).runs[0]).toMatchObject({ text: "Текст", bold: true });
  });
});
