import { useTranslation } from "react-i18next";
import type { DocumentPageExclusions, DocumentPageLayout } from "../../types/api";

type Props = {
  value?: DocumentPageExclusions;
  layout: DocumentPageLayout[];
  disabled: boolean;
  onChange: (value: DocumentPageExclusions) => void;
};

export function PageExclusionsPanel({ value, layout, disabled, onChange }: Props) {
  const { t } = useTranslation("documentChecks");
  const selected = new Set(value?.pages ?? []);
  const available = layout.length > 0 && layout.length <= 2000;
  return <fieldset disabled={disabled} className="rounded-xl border border-[var(--color-border)] p-3">
    <legend className="px-1 text-sm font-bold">{t("pageExclusionsTitle")}</legend>
    <p className="text-xs text-[var(--color-muted)]">{t("pageExclusionsHint")}</p>
    <p className="mt-2 text-xs font-semibold">{t("pageExclusionsSelected", { pages: [...selected].join(", ") || t("pageExclusionsNone") })}</p>
    {!available && <p role="status" className="mt-2 text-xs">{t(layout.length > 2000 ? "pageExclusionsLimit" : "pageExclusionsLoading")}</p>}
    {available && <div className="mt-3 grid max-h-44 grid-cols-2 gap-2 overflow-y-auto">
      {layout.map(page => <label key={page.number} className="flex items-center gap-2 text-xs">
        <input type="checkbox" checked={selected.has(page.number)} onChange={event => {
          const pages = new Set(selected);
          if (event.target.checked) pages.add(page.number); else pages.delete(page.number);
          onChange({ pages: [...pages].sort((a, b) => a - b), layout: pages.size ? layout : [] });
        }} />{t("previewPage", { number: page.number })}
      </label>)}
    </div>}
    {selected.size > 0 && <button type="button" className="mt-3 text-xs font-semibold underline" onClick={() => onChange({ pages: [], layout: [] })}>{t("pageExclusionsClear")}</button>}
  </fieldset>;
}
