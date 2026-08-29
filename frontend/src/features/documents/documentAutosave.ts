import { useCallback, useRef, useState } from "react";
import type { DocumentModel } from "../../types/document";
import { useDebouncedCallback } from "../../lib/useDebouncedCallback";
import type { SaveState } from "./SaveStatus";

const STALE_DOCUMENT_REVISION = "STALE_DOCUMENT_REVISION";

type ErrorWithResponse = {
  response?: {
    status?: number;
    data?: { detail?: { code?: string } };
  };
};

export function isDocumentRevisionConflict(error: unknown): boolean {
  const response = (error as ErrorWithResponse | undefined)?.response;
  return response?.status === 409 && response.data?.detail?.code === STALE_DOCUMENT_REVISION;
}

type RevisionedResult = { revision: number };

export function useDocumentAutosave<Document, Result extends RevisionedResult>({
  delayMs,
  save,
  onSaved,
  onConflict,
}: {
  delayMs: number;
  save: (document: Document, expectedRevision: number) => Promise<Result>;
  onSaved: (result: Result) => void;
  onConflict: () => void;
}) {
  const [state, setState] = useState<SaveState>("idle");
  const revisionRef = useRef<number | null>(null);
  const pendingDocumentRef = useRef<Document | null>(null);
  const isSavingRef = useRef(false);
  const pausedRef = useRef(false);
  const scheduleFlushRef = useRef<() => void>(() => undefined);

  const flush = useCallback(async () => {
    if (pausedRef.current || isSavingRef.current || pendingDocumentRef.current === null || revisionRef.current === null) return;

    const document = pendingDocumentRef.current;
    const expectedRevision = revisionRef.current;
    pendingDocumentRef.current = null;
    isSavingRef.current = true;
    setState("saving");

    try {
      const result = await save(document, expectedRevision);
      revisionRef.current = result.revision;
      onSaved(result);
      setState("saved");
    } catch (error) {
      if (isDocumentRevisionConflict(error)) {
        pausedRef.current = true;
        pendingDocumentRef.current = null;
        setState("idle");
        onConflict();
      } else {
        setState("error");
      }
    } finally {
      isSavingRef.current = false;
      if (!pausedRef.current && pendingDocumentRef.current !== null) scheduleFlushRef.current();
    }
  }, [onConflict, onSaved, save]);

  const delayedFlush = useDebouncedCallback(() => {
    void flush();
  }, delayMs);
  scheduleFlushRef.current = delayedFlush;

  const queueSave = useCallback(
    (document: Document) => {
      if (pausedRef.current) return;
      pendingDocumentRef.current = document;
      delayedFlush();
    },
    [delayedFlush]
  );

  const reset = useCallback((revision: number) => {
    pausedRef.current = false;
    pendingDocumentRef.current = null;
    revisionRef.current = revision;
    setState("idle");
  }, []);

  return { queueSave, reset, state };
}

export async function copyUnsavedDocument(document: DocumentModel): Promise<void> {
  const serialized = JSON.stringify(document, null, 2);
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(serialized);
    return;
  }

  const textarea = window.document.createElement("textarea");
  textarea.value = serialized;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  window.document.body.appendChild(textarea);
  textarea.select();
  const copied = window.document.execCommand("copy");
  textarea.remove();
  if (!copied) throw new Error("Clipboard copy is unavailable");
}
