import { Node, mergeAttributes } from "@tiptap/core";

/**
 * A 1:1 mirror of ParagraphBlock (app/documents/schemas.py). This is what
 * makes the Block <-> Tiptap conversion in converters.ts deterministic and
 * lossless — the node's attrs ARE the block's fields, nothing is invented
 * or approximated on the way in or out.
 *
 * Deep typographic properties (font, size, line spacing, indentation) stay
 * on the NAMED STYLE (style_name -> DocumentMeta.styles), edited via the
 * teacher's Page Settings panel — exactly how Word's paragraph styles work.
 * This node only exposes `alignment` as a direct per-paragraph override,
 * which is the one property people expect to toggle inline while writing.
 */
export const ParagraphNode = Node.create({
  name: "paragraph",
  group: "block",
  content: "inline*",

  addAttributes() {
    return {
      blockId: { default: null },
      styleName: { default: "Normal" },
      styleOverride: { default: null },
    };
  },

  parseHTML() {
    return [{ tag: "p" }];
  },

  renderHTML({ HTMLAttributes, node }) {
    const align = node.attrs.styleOverride?.alignment;
    const style = align ? `text-align: ${align}` : undefined;
    return ["p", mergeAttributes(HTMLAttributes, style ? { style } : {}), 0];
  },
});
