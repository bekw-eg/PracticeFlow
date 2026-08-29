import { describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { EditorContent } from "@tiptap/react";
import { useSectionEditor } from "../tiptap/useSectionEditor";
import { EditorToolbar } from "../tiptap/EditorToolbar";
import type { Block } from "../../../types/document";

function TestHarness({ blocks, editable, onBlocksChange }: { blocks: Block[]; editable: boolean; onBlocksChange: (b: Block[]) => void }) {
  const editor = useSectionEditor({ blocks, variableCatalog: [{ key: "student.full_name", label: "ФИО студента" }], editable, accessibleName: "Тестовый редактор", onBlocksChange });
  if (!editor) return null;
  return (
    <div>
      <EditorToolbar editor={editor} variableCatalog={[{ key: "student.full_name", label: "ФИО студента" }]} />
      <EditorContent editor={editor} />
    </div>
  );
}

const initialBlocks: Block[] = [
  { type: "paragraph", id: "p_1", style_name: "Normal", style_override: null, runs: [{ kind: "text", id: "r_1", text: "Some text", bold: false, italic: false, underline: false }] },
];

describe("Editing commands actually mutate the document (not just the toolbar UI)", () => {
  it("toggling Bold via the toolbar produces bold=true in the emitted Block[]", async () => {
    const onBlocksChange = vi.fn();
    let container: HTMLElement;
    await act(async () => {
      const result = render(<TestHarness blocks={initialBlocks} editable onBlocksChange={onBlocksChange} />);
      container = result.container;
    });

    const proseMirrorEl = container!.querySelector(".ProseMirror") as HTMLElement;
    expect(proseMirrorEl).toBeTruthy();

    await act(async () => {
      fireEvent.mouseDown(proseMirrorEl);
      fireEvent.keyDown(proseMirrorEl, { key: "a", ctrlKey: true });
    });

    await act(async () => {
      fireEvent.click(screen.getByTitle("Жирный"));
    });

    await waitFor(() => {
      expect(onBlocksChange).toHaveBeenCalled();
    });

    const lastCall = onBlocksChange.mock.calls.at(-1)![0] as Block[];
    const paragraph = lastCall[0] as Extract<Block, { type: "paragraph" }>;
    expect(paragraph.runs.some((r) => r.kind === "text" && r.bold === true)).toBe(true);
  });

  it("inserting a variable via the toolbar produces a VariableRun with the correct key", async () => {
    const onBlocksChange = vi.fn();
    await act(async () => {
      render(<TestHarness blocks={initialBlocks} editable onBlocksChange={onBlocksChange} />);
    });

    fireEvent.click(screen.getByTitle("Вставить переменную"));
    await act(async () => {
      fireEvent.click(screen.getByText("ФИО студента"));
    });

    await waitFor(() => expect(onBlocksChange).toHaveBeenCalled());
    const lastCall = onBlocksChange.mock.calls.at(-1)![0] as Block[];
    const paragraph = lastCall[0] as Extract<Block, { type: "paragraph" }>;
    expect(paragraph.runs.some((r) => r.kind === "variable" && r.key === "student.full_name")).toBe(true);
  });

  it("read-only mode (editable=false) renders a non-editable surface", async () => {
    const onBlocksChange = vi.fn();
    let container: HTMLElement;
    await act(async () => {
      const result = render(<TestHarness blocks={initialBlocks} editable={false} onBlocksChange={onBlocksChange} />);
      container = result.container;
    });
    const proseMirrorEl = container!.querySelector(".ProseMirror");
    expect(proseMirrorEl?.getAttribute("contenteditable")).toBe("false");
  });
});
