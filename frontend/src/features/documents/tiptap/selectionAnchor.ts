import type { Editor } from "@tiptap/react";

export interface SelectionAnchor {
  blockId: string;
  startOffset: number;
  endOffset: number;
  text: string;
}

/**
 * Translates the editor's current ProseMirror selection into the anchor
 * shape Phase 3 comments will need: a stable block id + character offsets
 * within that block's own text (never a screen coordinate, never a raw
 * ProseMirror document position, which would break the moment content
 * before it changes length).
 *
 * Returns null for selections that aren't a simple in-block text range
 * (empty selection, or one spanning multiple blocks/table cells) — exactly
 * the case comments don't support anyway.
 */
export function getSelectionAnchor(editor: Editor): SelectionAnchor | null {
  const { selection, doc } = editor.state;
  if (selection.empty) return null;

  const { $from, $to } = selection;
  const blockId = $from.parent.attrs?.blockId;
  if (!blockId) return null;

  // Selection must stay within the same block (same immediate parent node).
  if ($to.parent !== $from.parent) return null;

  const blockStart = $from.start();
  const startOffset = $from.pos - blockStart;
  const endOffset = $to.pos - blockStart;
  const text = doc.textBetween(selection.from, selection.to, " ");

  return { blockId, startOffset, endOffset, text };
}
