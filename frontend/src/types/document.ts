// Mirrors backend/app/documents/schemas.py exactly. Keep in sync manually —
// this is the one place the frontend's understanding of the document shape
// lives, so a component never invents its own partial view of a node.

export interface DocumentMargins {
  top_mm: number;
  bottom_mm: number;
  left_mm: number;
  right_mm: number;
}

export interface ParagraphStyle {
  alignment?: "left" | "center" | "right" | "justify" | null;
  line_spacing?: number | null;
  space_before_pt?: number | null;
  space_after_pt?: number | null;
  first_line_indent_mm?: number | null;
  left_indent_mm?: number | null;
  right_indent_mm?: number | null;
  font_family?: string | null;
  font_size_pt?: number | null;
  bold?: boolean | null;
  italic?: boolean | null;
  underline?: boolean | null;
}

export interface NumberingConfig {
  enabled: boolean;
  start_number: number;
  style: "decimal";
}

export interface DocumentMeta {
  page_size: "A4";
  orientation: "portrait" | "landscape";
  margins: DocumentMargins;
  default_font: string;
  default_font_size: number;
  line_spacing: number;
  styles: Record<string, ParagraphStyle>;
  numbering: NumberingConfig;
}

export interface TextRun {
  kind: "text";
  id: string;
  text: string;
  bold: boolean;
  italic: boolean;
  underline: boolean;
}

export interface VariableRun {
  kind: "variable";
  id: string;
  key: string;
  resolved_text: string | null;
}

export interface PageNumberRun {
  kind: "pageNumber";
  id: string;
}

export type Run = TextRun | VariableRun | PageNumberRun;

export interface ParagraphBlock {
  type: "paragraph";
  id: string;
  style_name: string;
  style_override: ParagraphStyle | null;
  runs: Run[];
}

export interface HeadingBlock {
  type: "heading";
  id: string;
  level: 1 | 2 | 3;
  style_name: string | null;
  runs: Run[];
  numbering: { participates: boolean };
}

export interface ImageBlock {
  type: "image";
  id: string;
  file_id: string | null;
  width_mm: number | null;
  alignment: "left" | "center" | "right";
  caption: string;
}

export interface PageBreakBlock {
  type: "pageBreak";
  id: string;
}

export interface TableCell {
  id: string;
  blocks: Block[];
}

export interface TableRow {
  id: string;
  cells: TableCell[];
}

export interface TableBlock {
  type: "table";
  id: string;
  rows: TableRow[];
}

export interface ListItem {
  id: string;
  blocks: Block[];
}

export interface ListBlock {
  type: "list";
  id: string;
  ordered: boolean;
  items: ListItem[];
}

export type Block = ParagraphBlock | HeadingBlock | ImageBlock | PageBreakBlock | TableBlock | ListBlock;

export interface Section {
  id: string;
  key: string;
  title: string;
  level: 1 | 2 | 3;
  required: boolean;
  editable: boolean;
  page_break_before: boolean;
  numbering: { participates: boolean };
  blocks: Block[];
}

export interface TitlePage {
  blocks: Block[];
}

export interface HeaderFooter {
  enabled: boolean;
  blocks: Block[];
}

export interface DocumentModel {
  schema_version: number;
  meta: DocumentMeta;
  title_page: TitlePage | null;
  header: HeaderFooter;
  footer: HeaderFooter;
  sections: Section[];
}

export interface TemplateVersionDetail {
  id: string;
  version_number: number;
  is_published: boolean;
  is_locked: boolean;
  created_at: string;
  document: DocumentModel;
  numbering: Record<string, string>;
  revision: number;
}

export interface ReportDocumentResponse {
  document: DocumentModel;
  numbering: Record<string, string>;
  editable: boolean;
  revision: number;
}

export interface VariableCatalogEntry {
  key: string;
  label: string;
}

export interface UploadedFile {
  id: string;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  url: string;
}
