import { ArrowPathIcon, ClipboardDocumentIcon, ExclamationTriangleIcon } from "@heroicons/react/24/outline";

export function DocumentConflictNotice({ onRefresh, onCopy, copyState }: { onRefresh: () => void; onCopy: () => void; copyState: "idle" | "copied" | "error" }) {
  return (
    <section role="alert" className="mb-5 rounded-2xl border border-[var(--color-danger-500)] bg-[var(--color-danger-50)] p-4 text-[var(--color-ink)]">
      <div className="flex items-start gap-3">
        <ExclamationTriangleIcon className="mt-0.5 size-5 shrink-0 text-[var(--color-danger-500)]" />
        <div>
          <h2 className="font-display font-bold">Документ был изменён в другой вкладке</h2>
          <p className="mt-1 text-sm">Автосохранение остановлено, чтобы не перезаписать актуальную версию. Сначала сохраните локальный черновик или обновите данные с сервера.</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <button type="button" onClick={onRefresh} className="btn btn-secondary">
              <ArrowPathIcon className="size-4" />Обновить данные
            </button>
            <button type="button" onClick={onCopy} className="btn btn-secondary">
              <ClipboardDocumentIcon className="size-4" />Скопировать несохранённые изменения
            </button>
          </div>
          {copyState === "copied" && <p className="mt-2 text-sm text-[var(--color-success-500)]">Несохранённые изменения скопированы в буфер обмена.</p>}
          {copyState === "error" && <p className="mt-2 text-sm text-[var(--color-danger-500)]">Не удалось скопировать изменения. Не закрывайте вкладку и скопируйте текст вручную.</p>}
        </div>
      </div>
    </section>
  );
}
