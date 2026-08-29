import { EditorContent } from "@tiptap/react";
import { LockClosedIcon } from "@heroicons/react/24/outline";
import type { Block, DocumentMeta, Section, VariableCatalogEntry } from "../../types/document";
import { BlockView } from "./BlockView";
import { useSectionEditor } from "./tiptap/useSectionEditor";
import { EditorToolbar } from "./tiptap/EditorToolbar";
import { NumberingProvider } from "./tiptap/NumberingContext";

/**
 * A section's `editable` flag (set by the teacher) decides everything here:
 * - editable  -> a real Tiptap rich-text editor, mounted only for this section
 * - locked    -> the plain read-only BlockView renderer, no editor at all
 *
 * This mirrors the backend boundary exactly: the student PATCH endpoint
 * only ever accepts blocks for sections where editable=true (see
 * app/services/report_service.py), so the frontend can't even construct a
 * request that touches a locked section — there is no editor instance to
 * produce one from.
 */
export function SectionEditor({
  section,
  numbering,
  meta,
  variableCatalog,
  allowVariableInsertion = true,
  canEdit,
  canEditTitle = false,
  onTitleChange,
  onBlocksChange,
}: {
  section: Section;
  numbering: Record<string, string>;
  meta: DocumentMeta;
  variableCatalog: VariableCatalogEntry[];
  allowVariableInsertion?: boolean;
  canEdit: boolean;
  canEditTitle?: boolean;
  onTitleChange?: (title: string) => void;
  onBlocksChange: (blocks: Block[]) => void;
}) {
  const isEditable = canEdit && section.editable;

  return (
    <div id={`node-${section.id}`} className="card mb-6 scroll-mt-24 p-4 sm:p-5">
      <div className="mb-3 flex items-center gap-2">
        <span className="text-sm font-semibold text-[var(--color-muted)]">{numbering[section.id]}</span>
        {canEditTitle ? (
          <input
            aria-label="Название раздела"
            value={section.title}
            onChange={(event) => onTitleChange?.(event.target.value)}
            className="min-w-0 flex-1 border-0 bg-transparent px-0 font-display font-bold text-[var(--color-ink)] outline-none focus:ring-0"
          />
        ) : (
          <h3 className="font-display font-bold text-[var(--color-ink)]">{section.title}</h3>
        )}
        {!section.editable && (
          <span className="ml-1 inline-flex items-center gap-1 rounded bg-[var(--color-surface)] px-1.5 py-0.5 text-[10px] text-[var(--color-muted)]">
            <LockClosedIcon className="size-3" /> закреплено преподавателем
          </span>
        )}
      </div>

      {isEditable ? (
        <NumberingProvider value={numbering}>
          <SectionRichTextEditor
            section={section}
            variableCatalog={variableCatalog}
            allowVariableInsertion={allowVariableInsertion}
            onBlocksChange={onBlocksChange}
          />
        </NumberingProvider>
      ) : (
        section.blocks.map((block) => <BlockView key={block.id} block={block} meta={meta} numberPrefix={numbering[block.id]} />)
      )}
    </div>
  );
}

function SectionRichTextEditor({
  section,
  variableCatalog,
  allowVariableInsertion,
  onBlocksChange,
}: {
  section: Section;
  variableCatalog: VariableCatalogEntry[];
  allowVariableInsertion: boolean;
  onBlocksChange: (blocks: Block[]) => void;
}) {
  const accessibleName = `Редактор раздела: ${section.title || "Без названия"}`;
  const editor = useSectionEditor({
    blocks: section.blocks,
    variableCatalog,
    editable: true,
    accessibleName,
    onBlocksChange,
  });

  if (!editor) return <p className="text-xs text-[var(--color-muted)]">Загрузка редактора…</p>;

  return (
    <div>
      <EditorToolbar editor={editor} variableCatalog={variableCatalog} allowVariableInsertion={allowVariableInsertion} />
      <div className="pf-editor-surface rounded-xl border border-[var(--color-border)] bg-white px-3 py-3 transition-shadow">
        <EditorContent editor={editor} />
      </div>
    </div>
  );
}
