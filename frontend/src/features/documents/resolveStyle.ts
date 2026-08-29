import type { DocumentMeta, HeadingBlock, ParagraphBlock, ParagraphStyle } from "../../types/document";

const ALIGNMENT_MAP: Record<string, React.CSSProperties["textAlign"]> = {
  left: "left",
  center: "center",
  right: "right",
  justify: "justify",
};

export function resolveStyle(meta: DocumentMeta, block: ParagraphBlock | HeadingBlock): React.CSSProperties {
  const styleName = block.type === "heading" ? block.style_name ?? `Heading${block.level}` : block.style_name;
  const named: ParagraphStyle = meta.styles[styleName] ?? {};
  const override: ParagraphStyle = block.type === "paragraph" ? block.style_override ?? {} : {};
  const merged: ParagraphStyle = { ...named, ...override };

  return {
    textAlign: ALIGNMENT_MAP[merged.alignment ?? "left"],
    lineHeight: merged.line_spacing ?? meta.line_spacing,
    marginTop: `${merged.space_before_pt ?? 0}pt`,
    marginBottom: `${merged.space_after_pt ?? 0}pt`,
    textIndent: `${merged.first_line_indent_mm ?? 0}mm`,
    marginLeft: `${merged.left_indent_mm ?? 0}mm`,
    marginRight: `${merged.right_indent_mm ?? 0}mm`,
    fontFamily: merged.font_family ?? meta.default_font,
    fontSize: `${merged.font_size_pt ?? meta.default_font_size}pt`,
    fontWeight: merged.bold ? 700 : 400,
    fontStyle: merged.italic ? "italic" : "normal",
    textDecoration: merged.underline ? "underline" : "none",
  };
}
