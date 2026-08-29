import { Node, mergeAttributes } from "@tiptap/core";

/**
 * Mirrors VariableRun. `label` is a display-time snapshot taken from the
 * variable catalog at insertion (rule 18: catalog stays server-defined;
 * this just avoids needing React context inside a static renderHTML). The
 * semantic value that round-trips to/from the PracticeFlow document is
 * `key` — `label` is cosmetic only.
 */
export const VariableNode = Node.create({
  name: "pfVariable",
  group: "inline",
  inline: true,
  atom: true,
  selectable: true,

  addAttributes() {
    return {
      runId: { default: null },
      key: { default: "" },
      label: { default: "" },
    };
  },

  parseHTML() {
    return [{ tag: "span[data-pf-variable]" }];
  },

  renderHTML({ HTMLAttributes, node }) {
    return [
      "span",
      mergeAttributes(HTMLAttributes, {
        "data-pf-variable": node.attrs.key,
        class: "pf-variable-chip",
        contenteditable: "false",
      }),
      node.attrs.label || node.attrs.key,
    ];
  },
});
