import type { DocumentMeta } from "../../types/document";
import { useTranslation } from "react-i18next";

export function PageSettingsPanel({ meta, onChange }: { meta: DocumentMeta; onChange: (meta: DocumentMeta) => void }) {
  const { t } = useTranslation("editor");
  return (
    <div className="section-panel p-5" role="region" aria-label={t("pageSettingsPanel")}>
      <h3 className="font-display mb-1 font-bold text-[var(--color-ink)]">{t("pageSettings")}</h3><p className="mb-4 text-xs leading-5 text-[var(--color-muted)]">{t("pageSettingsDescription")}</p>
      <div className="grid grid-cols-2 gap-3">
        <NumberField
          label={t("marginTop")}
          value={meta.margins.top_mm}
          onChange={(v) => onChange({ ...meta, margins: { ...meta.margins, top_mm: v } })}
        />
        <NumberField
          label={t("marginBottom")}
          value={meta.margins.bottom_mm}
          onChange={(v) => onChange({ ...meta, margins: { ...meta.margins, bottom_mm: v } })}
        />
        <NumberField
          label={t("marginLeft")}
          value={meta.margins.left_mm}
          onChange={(v) => onChange({ ...meta, margins: { ...meta.margins, left_mm: v } })}
        />
        <NumberField
          label={t("marginRight")}
          value={meta.margins.right_mm}
          onChange={(v) => onChange({ ...meta, margins: { ...meta.margins, right_mm: v } })}
        />
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3">
        <label className="block">
          <span className="mb-1 block text-xs font-semibold text-[var(--color-ink-soft)]">{t("font")}</span>
          <input value={meta.default_font} onChange={(e) => onChange({ ...meta, default_font: e.target.value })} className="input text-sm" />
        </label>
        <NumberField label={t("fontSize")} value={meta.default_font_size} onChange={(v) => onChange({ ...meta, default_font_size: v })} />
        <NumberField label={t("lineSpacing")} value={meta.line_spacing} step={0.1} onChange={(v) => onChange({ ...meta, line_spacing: v })} />
        <label className="block">
          <span className="mb-1 block text-xs font-semibold text-[var(--color-ink-soft)]">{t("orientation")}</span>
          <select
            value={meta.orientation}
            onChange={(e) => onChange({ ...meta, orientation: e.target.value as "portrait" | "landscape" })}
            className="input text-sm"
          >
            <option value="portrait">{t("portrait")}</option>
            <option value="landscape">{t("landscape")}</option>
          </select>
        </label>
      </div>

      <div className="mt-4 border-t border-[var(--color-border)] pt-4">
        <h4 className="mb-2 text-sm font-semibold text-[var(--color-ink)]">{t("autoNumbering")}</h4>
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-1.5 text-sm text-[var(--color-ink-soft)]">
            <input
              type="checkbox"
              checked={meta.numbering.enabled}
              onChange={(e) => onChange({ ...meta, numbering: { ...meta.numbering, enabled: e.target.checked } })}
            />
            {t("enabled")}
          </label>
          <NumberField
            label={t("startNumber")}
            value={meta.numbering.start_number}
            onChange={(v) => onChange({ ...meta, numbering: { ...meta.numbering, start_number: v } })}
          />
        </div>
      </div>
    </div>
  );
}

function NumberField({ label, value, onChange, step = 1 }: { label: string; value: number; onChange: (v: number) => void; step?: number }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-semibold text-[var(--color-ink-soft)]">{label}</span>
      <input
        type="number"
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="input text-sm"
      />
    </label>
  );
}
