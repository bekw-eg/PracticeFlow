import { Node, mergeAttributes } from "@tiptap/core";
import { ReactNodeViewRenderer } from "@tiptap/react";
import { ImageNodeView } from "./ImageNodeView";

/**
 * Mirrors ImageBlock. `fileId` is a StorageService-backed reference (never
 * a raw filesystem path — rule 24), resolved for display via
 * /api/v1/files/{fileId}, which itself enforces tenant ownership on every read.
 */
export const ImageNode = Node.create({
  name: "pfImage",
  group: "block",
  atom: true,
  selectable: true,

  addAttributes() {
    return {
      blockId: { default: null },
      fileId: { default: null },
      widthMm: { default: 100 },
      alignment: { default: "center" },
      caption: { default: "" },
    };
  },

  parseHTML() {
    return [{ tag: "div[data-pf-image]" }];
  },

  renderHTML({ HTMLAttributes }) {
    return ["div", mergeAttributes(HTMLAttributes, { "data-pf-image": "true" })];
  },

  addNodeView() {
    return ReactNodeViewRenderer(ImageNodeView);
  },
});
