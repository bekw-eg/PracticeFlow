import { Node, mergeAttributes } from "@tiptap/core";
import { ReactNodeViewRenderer } from "@tiptap/react";
import { HeadingNodeView } from "./HeadingNodeView";

/**
 * Mirrors HeadingBlock. Numbering is never stored or typed here — it's
 * rendered as a read-only prefix sourced from the server's numbering map
 * (see NumberingContext), so there is exactly one place the number "2.1"
 * gets computed, and the editor can never drift from it or let a student
 * type over it.
 */
export const HeadingNode = Node.create({
  name: "heading",
  group: "block",
  content: "inline*",
  defining: true,

  addAttributes() {
    return {
      blockId: { default: null },
      level: { default: 1 },
      styleName: { default: null },
      numberingParticipates: { default: true },
    };
  },

  parseHTML() {
    return [1, 2, 3].map((level) => ({ tag: `h${level}`, attrs: { level } }));
  },

  renderHTML({ node, HTMLAttributes }) {
    return [`h${node.attrs.level}`, mergeAttributes(HTMLAttributes), 0];
  },

  addNodeView() {
    return ReactNodeViewRenderer(HeadingNodeView);
  },
});
