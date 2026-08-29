import { Node, mergeAttributes } from "@tiptap/core";

/** Mirrors PageNumberRun — a structural page-number placeholder for
 * headers/footers (rule 21). Final pagination is Phase 3's concern. */
export const PageNumberNode = Node.create({
  name: "pfPageNumber",
  group: "inline",
  inline: true,
  atom: true,
  selectable: true,

  addAttributes() {
    return { runId: { default: null } };
  },

  parseHTML() {
    return [{ tag: "span[data-pf-page-number]" }];
  },

  renderHTML({ HTMLAttributes }) {
    return ["span", mergeAttributes(HTMLAttributes, { "data-pf-page-number": "true", class: "pf-pagenumber-chip", contenteditable: "false" }), "№"];
  },
});
