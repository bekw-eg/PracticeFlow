import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { EyeIcon, LockClosedIcon, ArrowLeftIcon } from "@heroicons/react/24/outline";
import { ErrorState, LoadingState } from "../../components/ui/StateViews";
import { useReportDocument, useSaveReportDocument } from "./api";
import { SectionEditor } from "./SectionEditor";
import { DocumentPreview } from "./DocumentPreview";
import { SaveStatus } from "./SaveStatus";
import { BlockView } from "./BlockView";
import { DocumentOutline } from "./DocumentOutline";
import { ExportButtons } from "../../components/ExportButtons";
import { ReportCollaborationPanel } from "../reports/ReportCollaborationPanel";
import type { Block, DocumentModel } from "../../types/document";
import { DocumentConflictNotice } from "./documentConflict";
import { copyUnsavedDocument, useDocumentAutosave } from "./documentAutosave";

export function ReportEditorPage() {
  const { reportId } = useParams<{ reportId: string }>();
  const { data, isLoading, isError, error, refetch } = useReportDocument(reportId);
  const saveMutation = useSaveReportDocument(reportId!);

  const [document, setDocument] = useState<DocumentModel | null>(null);
  const [numbering, setNumbering] = useState<Record<string, string>>({});
  const [hasConflict, setHasConflict] = useState(false);
  const [copyState, setCopyState] = useState<"idle" | "copied" | "error">("idle");
  const [showPreview, setShowPreview] = useState(false);
  const loadedRef = useRef(false);

  const { queueSave, reset: resetAutosave, state: saveState } = useDocumentAutosave({
    delayMs: 1500,
    save: (sections: Record<string, Block[]>, expectedRevision: number) =>
      saveMutation.mutateAsync({ sections, expectedRevision }),
    onSaved: (result) => setNumbering(result.numbering),
    onConflict: () => setHasConflict(true),
  });

  useEffect(() => {
    if (data && !loadedRef.current) {
      setDocument(data.document);
      setNumbering(data.numbering);
      resetAutosave(data.revision);
      loadedRef.current = true;
    }
  }, [data, resetAutosave]);

  const editable = data?.editable ?? false;

  const queueDocumentSave = (doc: DocumentModel) => {
    // Only ever send sections the student is actually allowed to touch —
    // the request shape itself is the enforcement (see backend
    // UpdateReportDocumentRequest / rule 15/16), so a locked section is
    // never even included in the payload.
    const sections: Record<string, Block[]> = {};
    for (const section of doc.sections) {
      if (section.editable) sections[section.id] = section.blocks;
    }
    queueSave(sections);
  };

  const updateSectionBlocks = (sectionId: string, blocks: Block[]) => {
    if (!document || hasConflict) return;
    const next = { ...document, sections: document.sections.map((s) => (s.id === sectionId ? { ...s, blocks } : s)) };
    setDocument(next);
    queueDocumentSave(next);
  };

  const refreshAfterConflict = async () => {
    const response = await refetch();
    if (!response.data) return;
    setDocument(response.data.document);
    setNumbering(response.data.numbering);
    resetAutosave(response.data.revision);
    setHasConflict(false);
    setCopyState("idle");
  };

  const copyLocalChanges = () => {
    if (!document) return;
    void copyUnsavedDocument(document).then(
      () => setCopyState("copied"),
      () => setCopyState("error")
    );
  };

  const previewNumbering = useMemo(() => numbering, [numbering]);

  if (isLoading || (!document && !isError && !data)) {
    return <LoadingState label="Загрузка отчёта…" />;
  }
  if (isError && !document) return <ErrorState error={error} onRetry={() => void refetch()} />;
  if (!document) return <LoadingState label="Подготовка редактора…" />;

  return (
    <div>
      <Link to="/reports" className="inline-flex items-center gap-1.5 text-sm font-semibold text-[var(--color-muted)] hover:text-[var(--color-brand-600)]">
        <ArrowLeftIcon className="size-4" />Мои отчёты
      </Link>

      <header className="mt-3 mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl font-bold text-[var(--color-ink)]">
            Отчёт по практике
            {!editable && (
              <span className="ml-3 inline-flex items-center gap-1 rounded-full bg-[var(--color-amber-50)] px-2.5 py-0.5 text-xs font-medium text-[var(--color-amber-500)]">
                <LockClosedIcon className="size-3.5" /> только чтение
              </span>
            )}
          </h1>
          <div className="mt-1">
            <SaveStatus state={editable && !hasConflict ? saveState : "idle"} />
          </div>
        </div>
        <button
          onClick={() => setShowPreview((v) => !v)}
          className="btn btn-secondary"
        >
          <EyeIcon className="size-4" />
          {showPreview ? "Редактор" : "Предпросмотр как A4"}
        </button>
        <ExportButtons reportId={reportId!} />
      </header>

      {isError && <div className="mb-5"><ErrorState compact error={error} onRetry={() => void refetch()} /></div>}
      {hasConflict && <DocumentConflictNotice onRefresh={() => void refreshAfterConflict()} onCopy={copyLocalChanges} copyState={copyState} />}

      {showPreview ? (
        <DocumentPreview document={document} numbering={previewNumbering} />
      ) : (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_260px]">
          <div>
            {document.title_page && (
              <div className="mb-6 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
                <p className="mb-2 text-xs font-medium uppercase tracking-wide text-[var(--color-muted)]">Титульный лист (задан преподавателем)</p>
                {document.title_page.blocks.map((b) => (
                  <BlockView key={b.id} block={b} meta={document.meta} />
                ))}
              </div>
            )}
            {document.sections.map((section) => (
              <SectionEditor
                key={section.id}
                section={section}
                numbering={previewNumbering}
                meta={document.meta}
                variableCatalog={[]}
                allowVariableInsertion={false}
                canEdit={editable && !hasConflict}
                onBlocksChange={(blocks: Block[]) => updateSectionBlocks(section.id, blocks)}
              />
            ))}
          </div>
          <div>
            <DocumentOutline document={document} numbering={previewNumbering} />
          </div>
        </div>
      )}
      <div className="mt-6 max-w-xl"><ReportCollaborationPanel reportId={reportId!} /></div>
    </div>
  );
}
