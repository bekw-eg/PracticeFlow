import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { PlusIcon, EyeIcon, LockClosedIcon, ArrowLeftIcon } from "@heroicons/react/24/outline";
import { ErrorState, LoadingState } from "../../components/ui/StateViews";
import { useSaveTemplateVersionDocument, useTemplateVersionDocument, useVariableCatalog } from "./api";
import { PageSettingsPanel } from "./PageSettingsPanel";
import { SectionEditor } from "./SectionEditor";
import { DocumentPreview } from "./DocumentPreview";
import { DocumentOutline } from "./DocumentOutline";
import { SaveStatus } from "./SaveStatus";
import { newNodeId } from "./nodeIds";
import type { Block, DocumentMeta, DocumentModel } from "../../types/document";
import { DocumentConflictNotice } from "./documentConflict";
import { copyUnsavedDocument, useDocumentAutosave } from "./documentAutosave";

export function TemplateEditorPage() {
  const { templateId, versionId } = useParams<{ templateId: string; versionId: string }>();
  const { data, isLoading, isError, error, refetch } = useTemplateVersionDocument(templateId, versionId);
  const saveMutation = useSaveTemplateVersionDocument(templateId!, versionId!);
  const { data: variableCatalog = [], isError: variableCatalogError, error: variableCatalogErrorValue, refetch: refetchVariableCatalog } = useVariableCatalog();

  const [document, setDocument] = useState<DocumentModel | null>(null);
  const [hasConflict, setHasConflict] = useState(false);
  const [copyState, setCopyState] = useState<"idle" | "copied" | "error">("idle");
  // Numbering is ALWAYS server-computed (app/documents/numbering.py) — there
  // is no client-side reimplementation (Phase 2 had one; it was a drift
  // risk and has been removed). Between saves the UI shows the last known
  // value from the server, refreshed automatically ~1.2s after any edit
  // that could change it (section/heading changes are the only edits that
  // do; plain text edits never touch these numbers at all).
  const [numbering, setNumbering] = useState<Record<string, string>>({});
  const [showPreview, setShowPreview] = useState(false);
  const loadedRef = useRef(false);

  const { queueSave, reset: resetAutosave, state: saveState } = useDocumentAutosave({
    delayMs: 1200,
    save: (nextDocument: DocumentModel, expectedRevision: number) =>
      saveMutation.mutateAsync({ document: nextDocument, expectedRevision }),
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

  const refreshAfterConflict = async () => {
    const response = await refetch();
    if (!response.data) return;
    setDocument(response.data.document);
    setNumbering(response.data.numbering);
    resetAutosave(response.data.revision);
    setHasConflict(false);
    setCopyState("idle");
  };

  const updateDocument = (next: DocumentModel) => {
    if (hasConflict) return;
    setDocument(next);
    queueSave(next);
  };

  const copyLocalChanges = () => {
    if (!document) return;
    void copyUnsavedDocument(document).then(
      () => setCopyState("copied"),
      () => setCopyState("error")
    );
  };

  if (isLoading || (!document && !isError && !data)) {
    return <LoadingState label="Загрузка редактора…" />;
  }
  if (isError && !document) return <ErrorState error={error} onRetry={() => void refetch()} />;
  if (!document) return <LoadingState label="Подготовка редактора…" />;

  const isLocked = data?.is_locked ?? false;
  const canEdit = !isLocked && !hasConflict;

  return (
    <div>
      <Link to="/templates" className="inline-flex items-center gap-1.5 text-sm font-semibold text-[var(--color-muted)] hover:text-[var(--color-brand-600)]">
        <ArrowLeftIcon className="size-4" />Шаблоны
      </Link>

      <header className="mt-4 mb-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="page-title">
            Версия {data?.version_number}
            {isLocked && (
              <span className="ml-3 inline-flex items-center gap-1 rounded-full bg-[var(--color-amber-50)] px-2.5 py-0.5 text-xs font-medium text-[var(--color-amber-500)]">
                <LockClosedIcon className="size-3.5" /> используется в практике — только чтение
              </span>
            )}
          </h1>
          <div className="mt-1">
            <SaveStatus state={isLocked || hasConflict ? "idle" : saveState} />
          </div>
        </div>
        <button
          onClick={() => setShowPreview((v) => !v)}
          className="btn btn-secondary"
        >
          <EyeIcon className="size-4" />
          {showPreview ? "Редактор" : "Предпросмотр"}
        </button>
      </header>

      {isError && <div className="mb-5"><ErrorState compact error={error} onRetry={() => void refetch()} /></div>}
      {variableCatalogError && <div className="mb-5"><ErrorState compact error={variableCatalogErrorValue} message="Список переменных недоступен. Редактирование документа продолжит работать, но вставка переменных временно отключена." onRetry={() => void refetchVariableCatalog()} /></div>}
      {hasConflict && <DocumentConflictNotice onRefresh={() => void refreshAfterConflict()} onCopy={copyLocalChanges} copyState={copyState} />}

      {showPreview ? (
        <DocumentPreview document={document} numbering={numbering} />
      ) : (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_280px]">
          <div>
            {document.sections.map((section) => (
              <SectionEditor
                key={section.id}
                section={section}
                numbering={numbering}
                meta={document.meta}
                variableCatalog={variableCatalog}
                canEdit={canEdit}
                canEditTitle={canEdit}
                onTitleChange={(title) =>
                  updateDocument({ ...document, sections: document.sections.map((s) => (s.id === section.id ? { ...s, title } : s)) })
                }
                onBlocksChange={(blocks: Block[]) =>
                  updateDocument({ ...document, sections: document.sections.map((s) => (s.id === section.id ? { ...s, blocks } : s)) })
                }
              />
            ))}
            {canEdit && (
              <button
                onClick={() =>
                  updateDocument({
                    ...document,
                    sections: [
                      ...document.sections,
                      {
                        id: newNodeId("sec"),
                        key: "",
                        title: "Новый раздел",
                        level: 1,
                        required: false,
                        editable: true,
                        page_break_before: true,
                        numbering: { participates: true },
                        blocks: [],
                      },
                    ],
                  })
                }
                className="btn border border-dashed border-[var(--color-border)] text-[var(--color-muted)] hover:border-[var(--color-brand-500)] hover:text-[var(--color-brand-600)]"
              >
                <PlusIcon className="size-4" />Добавить раздел
              </button>
            )}
          </div>
          <div className="space-y-4">
            <DocumentOutline document={document} numbering={numbering} />
            {canEdit && <PageSettingsPanel meta={document.meta} onChange={(meta: DocumentMeta) => updateDocument({ ...document, meta })} />}
            <SectionListSummary
              document={document}
              onToggleEditable={canEdit ? (id) => toggleSectionFlag(document, id, "editable", updateDocument) : undefined}
              onToggleRequired={canEdit ? (id) => toggleSectionFlag(document, id, "required", updateDocument) : undefined}
            />
          </div>
        </div>
      )}
    </div>
  );
}

function toggleSectionFlag(document: DocumentModel, sectionId: string, flag: "editable" | "required", update: (d: DocumentModel) => void) {
  update({
    ...document,
    sections: document.sections.map((s) => (s.id === sectionId ? { ...s, [flag]: !s[flag] } : s)),
  });
}

function SectionListSummary({
  document,
  onToggleEditable,
  onToggleRequired,
}: {
  document: DocumentModel;
  onToggleEditable?: (id: string) => void;
  onToggleRequired?: (id: string) => void;
}) {
  return (
    <div className="card p-5">
      <h3 className="font-display mb-3 font-bold text-[var(--color-ink)]">Структура документа</h3>
      <div className="space-y-2">
        {document.sections.map((section) => (
          <div key={section.id} className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-2.5 text-xs">
            <p className="mb-1 font-medium text-[var(--color-ink)]">{section.title || "Без названия"}</p>
            <label className="mr-3 inline-flex items-center gap-1 text-[var(--color-muted)]">
              <input type="checkbox" checked={section.required} disabled={!onToggleRequired} onChange={() => onToggleRequired?.(section.id)} />
              Обязательный
            </label>
            <label className="inline-flex items-center gap-1 text-[var(--color-muted)]">
              <input type="checkbox" checked={section.editable} disabled={!onToggleEditable} onChange={() => onToggleEditable?.(section.id)} />
              Редактируется студентом
            </label>
          </div>
        ))}
      </div>
    </div>
  );
}
