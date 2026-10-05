import type { CheckRuleType } from "../../types/api";

export const RULE_TYPES: CheckRuleType[] = ["PAGE_FORMAT_MARGINS", "FONTS_SIZES", "PARAGRAPH_SPACING_INDENTS", "HEADINGS", "TABLES", "FIGURE_CAPTIONS", "REFERENCES", "REQUIRED_SECTIONS", "SPELLING_LANGUAGES"];
export const EXECUTABLE_RULE_TYPES = new Set<CheckRuleType>(["PAGE_FORMAT_MARGINS", "FONTS_SIZES", "PARAGRAPH_SPACING_INDENTS", "HEADINGS"]);

export function defaultHeadingLevel(level: number) {
  return { level, allowed_fonts: ["Times New Roman"], min_size_pt: level === 1 ? 16 : 14, max_size_pt: level === 1 ? 16 : 14,
    bold: true, alignment: "CENTER", line_spacing: 1.5, space_before_pt: 0, space_after_pt: 0,
    first_line_indent_mm: 0, left_indent_mm: 0, right_indent_mm: 0 };
}

export function defaultConfig(type: CheckRuleType): Record<string, unknown> {
  switch (type) {
    case "PAGE_FORMAT_MARGINS": return { page_size: "A4", orientation: "PORTRAIT", margins: { top_mm: 20, right_mm: 15, bottom_mm: 20, left_mm: 30 }, width_mm: null, height_mm: null };
    case "FONTS_SIZES": return { allowed_fonts: ["Times New Roman"], min_size_pt: 14, max_size_pt: 14 };
    case "PARAGRAPH_SPACING_INDENTS": return { line_spacing: 1.5, space_before_pt: 0, space_after_pt: 0, first_line_indent_mm: 12.5, left_indent_mm: 0, right_indent_mm: 0, alignment: null };
    case "HEADINGS": return { levels: [1, 2, 3].map(defaultHeadingLevel), require_numbering: false };
    case "TABLES": return { require_header_row: true, require_caption: true, caption_position: "ABOVE", allowed_alignments: ["LEFT", "CENTER"] };
    case "FIGURE_CAPTIONS": return { required: true, position: "BELOW", numbering: "ARABIC", prefix: "Figure" };
    case "REFERENCES": return { style: "GOST", minimum_count: 5, require_in_text_citations: true, custom_style_name: null };
    case "REQUIRED_SECTIONS": return { sections: ["Introduction", "Conclusion"], case_sensitive: false };
    case "SPELLING_LANGUAGES": return { languages: ["en-US"], ignore_uppercase: true, ignore_urls: true };
  }
}
