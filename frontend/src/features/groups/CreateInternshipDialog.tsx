import { useState } from "react";
import { useTemplates, useCreateInternship } from "./api";
import { CalendarDaysIcon, XMarkIcon } from "@heroicons/react/24/outline";
import { ErrorState, LoadingState } from "../../components/ui/StateViews";

export function CreateInternshipDialog({ groupId, onClose }: { groupId: string; onClose: () => void }) {
  const { data: templates, isLoading: templatesLoading, isError: templatesError, error: templatesErrorValue, refetch: refetchTemplates } = useTemplates();
  const createInternship = useCreateInternship();

  const [title, setTitle] = useState("");
  const [templateVersionId, setTemplateVersionId] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [deadline, setDeadline] = useState("");
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    try {
      await createInternship.mutateAsync({
        groupId,
        title,
        template_version_id: templateVersionId,
        start_date: startDate,
        end_date: endDate,
        deadline,
      });
      onClose();
    } catch {
      setError("Не удалось создать практику. Проверьте заполненные поля.");
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--color-ink)]/35 px-4 backdrop-blur-[1px]" onClick={onClose}>
      <div
        className="w-full max-w-md rounded-2xl border border-[var(--color-border)] bg-[var(--color-card)] p-6 shadow-[var(--shadow-float)]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between"><div><div className="flex size-10 items-center justify-center rounded-xl bg-[var(--color-brand-50)] text-[var(--color-brand-600)]"><CalendarDaysIcon className="size-5" /></div><h2 className="mt-3 font-display text-lg font-bold text-[var(--color-ink)]">Новая практика</h2></div><button type="button" onClick={onClose} className="icon-button -mr-2 -mt-2" aria-label="Закрыть окно"><XMarkIcon className="size-5" /></button></div>
        <p className="mt-1 text-sm text-[var(--color-muted)]">Выберите существующий шаблон или создайте новый в разделе «Шаблоны».</p>

        <form onSubmit={handleSubmit} className="mt-4 space-y-3">
          <label className="block">
            <span className="form-label">Название</span>
            <input value={title} onChange={(e) => setTitle(e.target.value)} className="input" required />
          </label>
          {templatesLoading && <LoadingState label="Загрузка шаблонов…" />}
          {templatesError && <ErrorState compact error={templatesErrorValue} message="Не удалось загрузить шаблоны для новой практики." onRetry={() => void refetchTemplates()} />}

          <label className="block">
            <span className="form-label">Шаблон (версия)</span>
            <select value={templateVersionId} onChange={(e) => setTemplateVersionId(e.target.value)} className="input" required>
              <option value="" disabled>
                Выберите шаблон…
              </option>
              {templates?.items.map((template) =>
                template.versions.map((version) => (
                  <option key={version.id} value={version.id}>
                    {template.name} · v{version.version_number}
                  </option>
                ))
              )}
            </select>
          </label>

          <div className="grid gap-3 sm:grid-cols-3">
            <label className="block">
              <span className="form-label">Начало</span>
              <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="input" required />
            </label>
            <label className="block">
              <span className="form-label">Конец</span>
              <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="input" required />
            </label>
            <label className="block">
              <span className="form-label">Дедлайн</span>
              <input type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)} className="input" required />
            </label>
          </div>

          {error && <p className="rounded-lg bg-[var(--color-danger-50)] px-3 py-2 text-sm text-[var(--color-danger-500)]">{error}</p>}

          <div className="mt-2 flex justify-end gap-2">
            <button type="button" onClick={onClose} className="btn btn-ghost">
              Отмена
            </button>
            <button
              type="submit"
            disabled={createInternship.isPending || templatesError || templatesLoading}
              className="btn btn-primary"
            >
              {createInternship.isPending ? "Создание…" : "Создать"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
