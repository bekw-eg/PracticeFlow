import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useTemplates, useCreateInternship } from "./api";
import { CalendarDaysIcon, XMarkIcon } from "@heroicons/react/24/outline";
import { ErrorState, LoadingState } from "../../components/ui/StateViews";
import { useLocaleFormatters } from "../../i18n/formatters";
import { getApiErrorPresentation } from "../../lib/apiError";

const MAX_INTERNSHIP_DESCRIPTION_LENGTH = 2000;

export function CreateInternshipDialog({
  groupId,
  onClose,
}: {
  groupId: string;
  onClose: () => void;
}) {
  const { t } = useTranslation(["groups", "templates", "common", "editor"]);
  const { formatNumber } = useLocaleFormatters();
  const {
    data: templates,
    isLoading: templatesLoading,
    isError: templatesError,
    error: templatesErrorValue,
    refetch: refetchTemplates,
  } = useTemplates();
  const createInternship = useCreateInternship();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [templateVersionId, setTemplateVersionId] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [deadline, setDeadline] = useState("");
  const [error, setError] = useState<string | null>(null);
  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    if (description.length > MAX_INTERNSHIP_DESCRIPTION_LENGTH) {
      setError(t("groups:internshipDescriptionTooLong", { max: formatNumber(MAX_INTERNSHIP_DESCRIPTION_LENGTH) }));
      return;
    }
    try {
      await createInternship.mutateAsync({
        groupId,
        title,
        description: description.trim() || undefined,
        template_version_id: templateVersionId,
        start_date: startDate,
        end_date: endDate,
        deadline,
      });
      onClose();
    } catch (caught) {
      setError(getApiErrorPresentation(caught, "internships").description);
    }
  };
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--color-ink)]/35 px-4 backdrop-blur-[1px]"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-label={t("groups:newInternship")}
        className="w-full max-w-md rounded-2xl border border-[var(--color-border)] bg-[var(--color-card)] p-6 shadow-[var(--shadow-float)]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between">
          <div>
            <div className="flex size-10 items-center justify-center rounded-xl bg-[var(--color-brand-50)] text-[var(--color-brand-600)]">
              <CalendarDaysIcon aria-hidden="true" className="size-5" />
            </div>
            <h2 className="mt-3 font-display text-lg font-bold text-[var(--color-ink)]">
              {t("groups:newInternship")}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="icon-button -mr-2 -mt-2"
            aria-label={t("common:closeDialog")}
          >
            <XMarkIcon aria-hidden="true" className="size-5" />
          </button>
        </div>
        <p className="mt-1 text-sm text-[var(--color-muted)]">
          {t("groups:createInternshipDescription")}
        </p>
        <form onSubmit={handleSubmit} className="mt-4 space-y-3">
          <label className="block">
            <span className="form-label">{t("common:name")}</span>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="input"
              required
            />
          </label>
          <div>
            <label className="block" htmlFor="internship-description">
              <span className="form-label">{t("groups:internshipDescriptionLabel")}</span>
              <textarea
                id="internship-description"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                className="input min-h-28 resize-y"
                maxLength={MAX_INTERNSHIP_DESCRIPTION_LENGTH}
                aria-describedby="internship-description-help internship-description-count"
              />
            </label>
            <p id="internship-description-help" className="mt-1 text-xs leading-5 text-[var(--color-muted)]">
              {t("groups:internshipDescriptionHelp")}
            </p>
            <p id="internship-description-count" className="mt-1 text-right text-xs text-[var(--color-muted)]">
              {t("groups:internshipDescriptionCount", { count: formatNumber(description.length), max: formatNumber(MAX_INTERNSHIP_DESCRIPTION_LENGTH) })}
            </p>
          </div>
          {templatesLoading && (
            <LoadingState label={t("templates:loadingTemplates")} />
          )}
          {templatesError && (
            <ErrorState
              compact
              error={templatesErrorValue}
              message={t("groups:createInternshipError")}
              onRetry={() => void refetchTemplates()}
            />
          )}
          <label className="block">
            <span className="form-label">{t("groups:templateVersion")}</span>
            <select
              value={templateVersionId}
              onChange={(e) => setTemplateVersionId(e.target.value)}
              className="input"
              required
            >
              <option value="" disabled>
                {t("groups:chooseTemplate")}
              </option>
              {templates?.items.map((template) =>
                template.versions.map((version) => (
                  <option key={version.id} value={version.id}>
                          {template.name} · {t("editor:templateVersion", { version: formatNumber(version.version_number) })}
                  </option>
                )),
              )}
            </select>
          </label>
          <div className="grid gap-3 sm:grid-cols-3">
            <DateField
              label={t("groups:startDate")}
              value={startDate}
              onChange={setStartDate}
            />
            <DateField
              label={t("groups:endDate")}
              value={endDate}
              onChange={setEndDate}
            />
            <DateField
              label={t("groups:deadline")}
              value={deadline}
              onChange={setDeadline}
            />
          </div>
          {error && (
            <div className="rounded-lg bg-[var(--color-danger-50)] px-3 py-2 text-sm text-[var(--color-danger-500)]" role="alert">
              <p className="font-semibold">{t("groups:createInternshipError")}</p>
              <p className="mt-1">{error}</p>
            </div>
          )}
          <div className="mt-2 flex justify-end gap-2">
            <button type="button" onClick={onClose} className="btn btn-ghost">
              {t("common:cancel")}
            </button>
            <button
              type="submit"
              disabled={
                createInternship.isPending || templatesError || templatesLoading
              }
              className="btn btn-primary"
            >
              {createInternship.isPending
                ? t("groups:creating")
                : t("common:create")}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function DateField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="block">
      <span className="form-label">{label}</span>
      <input
        type="date"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="input"
        required
      />
    </label>
  );
}
