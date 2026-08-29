import type { DocumentMeta } from "../../types/document";

export function PageSettingsPanel({ meta, onChange }: { meta: DocumentMeta; onChange: (meta: DocumentMeta) => void }) {
  return (
    <div className="card p-5">
      <h3 className="font-display mb-1 font-bold text-[var(--color-ink)]">Параметры страницы</h3><p className="mb-4 text-xs leading-5 text-[var(--color-muted)]">Единые параметры применяются ко всему документу.</p>
      <div className="grid grid-cols-2 gap-3">
        <NumberField
          label="Поле сверху (мм)"
          value={meta.margins.top_mm}
          onChange={(v) => onChange({ ...meta, margins: { ...meta.margins, top_mm: v } })}
        />
        <NumberField
          label="Поле снизу (мм)"
          value={meta.margins.bottom_mm}
          onChange={(v) => onChange({ ...meta, margins: { ...meta.margins, bottom_mm: v } })}
        />
        <NumberField
          label="Поле слева (мм)"
          value={meta.margins.left_mm}
          onChange={(v) => onChange({ ...meta, margins: { ...meta.margins, left_mm: v } })}
        />
        <NumberField
          label="Поле справа (мм)"
          value={meta.margins.right_mm}
          onChange={(v) => onChange({ ...meta, margins: { ...meta.margins, right_mm: v } })}
        />
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3">
        <label className="block">
          <span className="mb-1 block text-xs font-semibold text-[var(--color-ink-soft)]">Шрифт</span>
          <input value={meta.default_font} onChange={(e) => onChange({ ...meta, default_font: e.target.value })} className="input text-sm" />
        </label>
        <NumberField label="Размер шрифта (pt)" value={meta.default_font_size} onChange={(v) => onChange({ ...meta, default_font_size: v })} />
        <NumberField label="Межстрочный интервал" value={meta.line_spacing} step={0.1} onChange={(v) => onChange({ ...meta, line_spacing: v })} />
        <label className="block">
          <span className="mb-1 block text-xs font-semibold text-[var(--color-ink-soft)]">Ориентация</span>
          <select
            value={meta.orientation}
            onChange={(e) => onChange({ ...meta, orientation: e.target.value as "portrait" | "landscape" })}
            className="input text-sm"
          >
            <option value="portrait">Книжная</option>
            <option value="landscape">Альбомная</option>
          </select>
        </label>
      </div>

      <div className="mt-4 border-t border-[var(--color-border)] pt-4">
        <h4 className="mb-2 text-sm font-semibold text-[var(--color-ink)]">Автонумерация</h4>
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-1.5 text-sm text-[var(--color-ink-soft)]">
            <input
              type="checkbox"
              checked={meta.numbering.enabled}
              onChange={(e) => onChange({ ...meta, numbering: { ...meta.numbering, enabled: e.target.checked } })}
            />
            Включена
          </label>
          <NumberField
            label="Начальный номер"
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
