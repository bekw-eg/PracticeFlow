import { NodeViewContent, NodeViewWrapper, type NodeViewProps } from "@tiptap/react";

import { useNumbering } from "./useNumbering";

export function HeadingNodeView({ node }: NodeViewProps) {
  const number = useNumbering(node.attrs.blockId);
  const Tag = `h${node.attrs.level}` as "h1" | "h2" | "h3";
  const sizePt = node.attrs.level === 1 ? "16pt" : "14pt";

  return (
    <NodeViewWrapper as={Tag} id={`node-${node.attrs.blockId}`} style={{ fontSize: sizePt, fontWeight: 700, margin: "12pt 0 8pt" }}>
      {number && (
        <span contentEditable={false} className="mr-2 select-none text-[var(--color-muted)]">
          {number}
        </span>
      )}
      <NodeViewContent<"span"> as="span" />
    </NodeViewWrapper>
  );
}
