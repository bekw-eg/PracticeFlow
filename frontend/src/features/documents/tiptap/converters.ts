import type { JSONContent } from "@tiptap/core";
import type { Block, Run, TableCell as PfTableCell, TableRow as PfTableRow, VariableCatalogEntry } from "../../../types/document";
import { newNodeId } from "../nodeIds";

// --- PracticeFlow Block[] -> Tiptap JSON ---

function runToTiptapNode(run: Run, catalog: VariableCatalogEntry[]): JSONContent {
  if (run.kind === "text") {
    const marks: JSONContent["marks"] = [];
    if (run.bold) marks.push({ type: "bold" });
    if (run.italic) marks.push({ type: "italic" });
    if (run.underline) marks.push({ type: "underline" });
    if (!run.text) return { type: "text", text: "\u200b" };
    return { type: "text", text: run.text, marks: marks.length ? marks : undefined };
  }
  if (run.kind === "variable") {
    const label = catalog.find((v) => v.key === run.key)?.label ?? run.key;
    return { type: "pfVariable", attrs: { runId: run.id, key: run.key, label } };
  }
  return { type: "pfPageNumber", attrs: { runId: run.id } };
}

export function blockToTiptapNode(block: Block, catalog: VariableCatalogEntry[]): JSONContent {
  switch (block.type) {
    case "paragraph":
      return {
        type: "paragraph",
        // Keep the complete block style in the editor JSON. The toolbar only
        // edits alignment today, but dropping the remaining overrides on
        // every Tiptap update made the preview/export diverge from the saved
        // document formatting.
        attrs: { blockId: block.id, styleName: block.style_name, styleOverride: block.style_override },
        content: block.runs.length ? block.runs.map((r) => runToTiptapNode(r, catalog)) : [{ type: "text", text: "\u200b" }],
      };
    case "heading":
      return {
        type: "heading",
        attrs: { blockId: block.id, level: block.level, styleName: block.style_name, numberingParticipates: block.numbering.participates },
        content: block.runs.length ? block.runs.map((r) => runToTiptapNode(r, catalog)) : [{ type: "text", text: "\u200b" }],
      };
    case "image":
      return { type: "pfImage", attrs: { blockId: block.id, fileId: block.file_id, widthMm: block.width_mm, alignment: block.alignment, caption: block.caption } };
    case "pageBreak":
      return { type: "pfPageBreak", attrs: { blockId: block.id } };
    case "table":
      return {
        type: "table",
        attrs: { blockId: block.id },
        content: block.rows.map((row) => ({
          type: "tableRow",
          attrs: { rowId: row.id },
          content: row.cells.map((cell) => ({
            type: "tableCell",
            attrs: { cellId: cell.id },
            content: cell.blocks.map((b) => blockToTiptapNode(b, catalog)),
          })),
        })),
      };
    case "list":
      return {
        type: block.ordered ? "orderedList" : "bulletList",
        attrs: { blockId: block.id },
        content: block.items.map((item) => ({
          type: "listItem",
          attrs: { itemId: item.id },
          content: item.blocks.map((b) => blockToTiptapNode(b, catalog)),
        })),
      };
  }
}

export function blocksToTiptapDoc(blocks: Block[], catalog: VariableCatalogEntry[]): JSONContent {
  return {
    type: "doc",
    content: blocks.length ? blocks.map((b) => blockToTiptapNode(b, catalog)) : [{ type: "paragraph", attrs: { blockId: newNodeId("p") }, content: [{ type: "text", text: "\u200b" }] }],
  };
}

// --- Tiptap JSON -> PracticeFlow Block[] ---

function tiptapNodeToRun(node: JSONContent): Run | null {
  if (node.type === "text") {
    const text = (node.text ?? "").replace(/\u200b/g, "");
    const marks = node.marks ?? [];
    return {
      kind: "text",
      id: newNodeId("run"),
      text,
      bold: marks.some((m) => m.type === "bold"),
      italic: marks.some((m) => m.type === "italic"),
      underline: marks.some((m) => m.type === "underline"),
    };
  }
  if (node.type === "pfVariable") {
    return { kind: "variable", id: node.attrs?.runId || newNodeId("var"), key: node.attrs?.key ?? "", resolved_text: null };
  }
  if (node.type === "pfPageNumber") {
    return { kind: "pageNumber", id: node.attrs?.runId || newNodeId("pn") };
  }
  return null;
}

function collectRuns(content: JSONContent[] | undefined): Run[] {
  const runs = (content ?? []).map(tiptapNodeToRun).filter((r): r is Run => r !== null);
  if (runs.length <= 1) return runs;
  return runs.filter((r) => !(r.kind === "text" && r.text === ""));
}

export function tiptapNodeToBlock(node: JSONContent): Block {
  switch (node.type) {
    case "paragraph":
      return {
        type: "paragraph",
        id: node.attrs?.blockId || newNodeId("p"),
        style_name: node.attrs?.styleName || "Normal",
        style_override: node.attrs?.styleOverride ?? null,
        runs: collectRuns(node.content),
      };
    case "heading":
      return {
        type: "heading",
        id: node.attrs?.blockId || newNodeId("h"),
        level: (node.attrs?.level ?? 1) as 1 | 2 | 3,
        style_name: node.attrs?.styleName ?? null,
        runs: collectRuns(node.content),
        numbering: { participates: node.attrs?.numberingParticipates ?? true },
      };
    case "pfImage":
      return {
        type: "image",
        id: node.attrs?.blockId || newNodeId("img"),
        file_id: node.attrs?.fileId ?? null,
        width_mm: node.attrs?.widthMm ?? null,
        alignment: node.attrs?.alignment ?? "center",
        caption: node.attrs?.caption ?? "",
      };
    case "pfPageBreak":
      return { type: "pageBreak", id: node.attrs?.blockId || newNodeId("brk") };
    case "table": {
      const rows: PfTableRow[] = (node.content ?? []).map((row) => ({
        id: row.attrs?.rowId || newNodeId("row"),
        cells: (row.content ?? []).map(
          (cell): PfTableCell => ({
            id: cell.attrs?.cellId || newNodeId("cell"),
            blocks: (cell.content ?? []).map(tiptapNodeToBlock),
          })
        ),
      }));
      return { type: "table", id: node.attrs?.blockId || newNodeId("tbl"), rows };
    }
    case "bulletList":
    case "orderedList":
      return {
        type: "list",
        id: node.attrs?.blockId || newNodeId("list"),
        ordered: node.type === "orderedList",
        items: (node.content ?? []).map((item) => ({
          id: item.attrs?.itemId || newNodeId("li"),
          blocks: (item.content ?? []).map(tiptapNodeToBlock),
        })),
      };
    default:
      return { type: "paragraph", id: newNodeId("p"), style_name: "Normal", style_override: null, runs: [] };
  }
}

export function tiptapDocToBlocks(doc: JSONContent): Block[] {
  return (doc.content ?? []).map(tiptapNodeToBlock);
}
