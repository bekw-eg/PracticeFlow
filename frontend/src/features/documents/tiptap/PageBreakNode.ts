import { Node, mergeAttributes } from "@tiptap/core";

/** Mirrors PageBreakBlock — an explicit break the teacher/student inserts
 * so a major section starts on a new page (rule 22). */
export const PageBreakNode = Node.create({
  name: "pfPageBreak",
  group: "block",
  atom: true,
  selectable: true,

  addAttributes() {
    return { blockId: { default: null } };
  },

  parseHTML() {
    return [{ tag: "div[data-pf-page-break]" }];
  },

  renderHTML({ HTMLAttributes }) {
    return ["div", mergeAttributes(HTMLAttributes, { "data-pf-page-break": "true", class: "pf-pagebreak" })];
  },
});
