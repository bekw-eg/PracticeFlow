import { useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Placeholder from "@tiptap/extension-placeholder";
import { TableKit } from "@tiptap/extension-table";
import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import type { Block, VariableCatalogEntry } from "../../../types/document";
import { ParagraphNode } from "./ParagraphNode";
import { HeadingNode } from "./HeadingNode";
import { VariableNode } from "./VariableNode";
import { PageNumberNode } from "./PageNumberNode";
import { ImageNode } from "./ImageNode";
import { PageBreakNode } from "./PageBreakNode";
import { blocksToTiptapDoc, tiptapDocToBlocks } from "./converters";

/**
 * One editor instance per EDITABLE section (mirrors the existing per-section
 * boundary from Phase 2's SectionEditor). A locked section never gets an
 * editor at all — it stays on the plain read-only BlockView renderer.
 */
export function useSectionEditor({
  blocks,
  variableCatalog,
  editable,
  accessibleName,
  onBlocksChange,
}: {
  blocks: Block[];
  variableCatalog: VariableCatalogEntry[];
  editable: boolean;
  accessibleName: string;
  onBlocksChange: (blocks: Block[]) => void;
}) {
  const { t } = useTranslation("editor");
  // Only the FIRST render's content seeds the editor — subsequent prop
  // changes to `blocks` come from OUR OWN onUpdate round-trip, never from
  // outside, so we deliberately do not resync content on every prop change:
  // that would fight the user's live cursor position on every keystroke.
  const initialDoc = useRef(blocksToTiptapDoc(blocks, variableCatalog));

  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        paragraph: false,
        heading: false,
        strike: false,
        code: false,
        codeBlock: false,
        blockquote: false,
        horizontalRule: false,
        link: false,
      }),
      Placeholder.configure({ placeholder: t("startTyping") }),
      TableKit.configure({ table: { resizable: false } }),
      ParagraphNode,
      HeadingNode,
      VariableNode,
      PageNumberNode,
      ImageNode,
      PageBreakNode,
    ],
    content: initialDoc.current,
    editable,
    editorProps: {
      attributes: {
        role: "textbox",
        "aria-label": accessibleName,
        "aria-multiline": "true",
      },
    },
    onUpdate: ({ editor }) => {
      onBlocksChange(tiptapDocToBlocks(editor.getJSON()));
    },
  });

  useEffect(() => {
    editor?.setEditable(editable);
  }, [editable, editor]);

  useEffect(() => {
    if (!editor) return;
    editor.view.dom.setAttribute("aria-label", accessibleName);
  }, [accessibleName, editor]);

  return editor;
}
