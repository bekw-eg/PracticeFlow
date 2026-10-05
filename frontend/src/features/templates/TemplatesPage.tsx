import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  PlusIcon,
  LockClosedIcon,
  DocumentTextIcon,
} from "@heroicons/react/24/outline";
import {
  LoadingState,
  EmptyState,
  ErrorState,
} from "../../components/ui/StateViews";
import { PaginationControls } from "../../components/ui/PaginationControls";
import { api } from "../../lib/api";
import { useTemplates } from "../groups/api";
import { useTranslation } from "react-i18next";
import { useLocaleFormatters } from "../../i18n/formatters";
import { useProductFeatures } from "../auth/useProductFeatures";

export function TemplatesPage() {
  const { t } = useTranslation(["templates", "common", "editor"]);
  const { formatNumber } = useLocaleFormatters();
  const { legacy_document_editor_enabled: legacyDocumentEditorEnabled } = useProductFeatures();
  const [searchParams, setSearchParams] = useSearchParams();
  const offset = Math.max(0, Number(searchParams.get("offset") ?? "0") || 0);
  const {
    data: page,
    isLoading,
    isFetching,
    isError,
    error,
    refetch,
  } = useTemplates(offset);
  const templates = page?.items ?? [];
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [isCreating, setIsCreating] = useState(false);

  const createTemplate = useMutation({
    mutationFn: async () => (await api.post("/templates", { name })).data,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["templates"] });
      setName("");
      setIsCreating(false);
    },
  });

  const createVersion = useMutation({
    mutationFn: async (templateId: string) =>
      (await api.post(`/templates/${templateId}/versions`, {})).data,
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: ["templates"] }),
  });
  const changePage = (nextOffset: number) => {
    const next = new URLSearchParams(searchParams);
    if (nextOffset === 0) next.delete("offset");
    else next.set("offset", String(nextOffset));
    setSearchParams(next);
  };

  return (
    <div>
      <header className="mb-7 flex flex-wrap items-end justify-between gap-4 border-b border-[var(--color-border)] pb-6">
        <div>
          <p className="page-kicker">{t("templates:documentLibrary")}</p>
          <h1 className="page-title mt-1">{t("templates:reportTemplates")}</h1>
          <p className="page-description">{t("templates:description")}</p>
        </div>
        {legacyDocumentEditorEnabled && (
          <button onClick={() => setIsCreating(true)} className="btn btn-primary">
            <PlusIcon className="size-4" />
            {t("templates:template")}
          </button>
        )}
      </header>

      {legacyDocumentEditorEnabled && isCreating && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            createTemplate.mutate();
          }}
          className="section-panel mb-6 flex flex-col gap-3 p-4 sm:flex-row"
        >
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={t("templates:templateName")}
            className="input"
            autoFocus
            required
          />
          <button
            type="submit"
            disabled={createTemplate.isPending}
            className="btn btn-primary shrink-0"
          >
            {t("common:create")}
          </button>
          <button
            type="button"
            onClick={() => setIsCreating(false)}
            className="btn btn-ghost shrink-0"
          >
            {t("common:cancel")}
          </button>
        </form>
      )}

      {isLoading && <LoadingState label={t("templates:loadingTemplates")} />}

      {isError && <ErrorState error={error} onRetry={() => void refetch()} />}

      {!isLoading && !isError && templates?.length === 0 && (
        <EmptyState
          title={t("templates:noTemplates")}
          description={t("templates:noTemplatesDescription")}
        />
      )}

      {templates.length > 0 && <div className="section-panel divide-y divide-[var(--color-border)] overflow-hidden">
        {!isError &&
          templates?.map((template) => (
            <div key={template.id} className="bg-white p-5 sm:p-6">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="flex size-10 items-center justify-center rounded-[7px] border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-brand-600)]">
                    <DocumentTextIcon className="size-5" />
                  </div>
                  <h3 className="font-display font-bold text-[var(--color-ink)]">
                    {template.name}
                  </h3>
                </div>
                {legacyDocumentEditorEnabled && (
                  <button
                    onClick={() => createVersion.mutate(template.id)}
                    disabled={createVersion.isPending}
                    className="btn btn-ghost px-2 py-1.5 text-xs text-[var(--color-brand-600)]"
                  >
                    <PlusIcon className="size-4" />
                    {t("templates:newVersion")}
                  </button>
                )}
              </div>
              {template.description && (
                <p className="mt-1 text-sm text-[var(--color-muted)]">
                  {template.description}
                </p>
              )}
              <div className="mt-3 flex flex-wrap gap-1.5">
                {template.versions.map((v) => (
                  <Link
                    key={v.id}
                    to={`/templates/${template.id}/versions/${v.id}`}
                    className="font-mono-code inline-flex items-center gap-1.5 rounded-[5px] border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-1.5 text-xs font-semibold text-[var(--color-ink-soft)] transition-colors hover:border-[var(--color-brand-500)] hover:bg-[var(--color-brand-50)] hover:text-[var(--color-brand-600)]"
                  >
                  {t("editor:templateVersion", { version: formatNumber(v.version_number) })}
                    {v.is_locked && <LockClosedIcon className="size-3" />}
                  </Link>
                ))}
              </div>
            </div>
          ))}
      </div>}
      {!isError && page && (
        <PaginationControls
          pagination={page}
          onPageChange={changePage}
          isFetching={isFetching}
          label={t("templates:templates")}
        />
      )}
    </div>
  );
}
