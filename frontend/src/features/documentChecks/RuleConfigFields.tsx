import { useEffect, useState, type ChangeEvent } from "react";
import { useTranslation } from "react-i18next";
import type { CheckRuleType } from "../../types/api";
import { defaultHeadingLevel } from "./ruleConfig";

type Config = Record<string, unknown>;
type Props = { type: CheckRuleType; config: Config; disabled: boolean; patch: (value: Config) => void };
const SPACING = ["line_spacing", "space_before_pt", "space_after_pt", "first_line_indent_mm", "left_indent_mm", "right_indent_mm"];
const ALIGNMENTS = ["LEFT", "CENTER", "RIGHT", "JUSTIFY"];

function ListField({ label, value, disabled, onChange, multiline = false }: {
  label: string; value: unknown; disabled: boolean; onChange: (value: string[]) => void; multiline?: boolean;
}) {
  const separator = multiline ? "\n" : ", ";
  const canonical = Array.isArray(value) ? value.join(separator) : "";
  const [raw, setRaw] = useState(canonical);
  useEffect(() => { setRaw(current => {
    const normalized = current.split(multiline ? "\n" : ",").map(v => v.trim()).filter(Boolean).join(separator);
    return normalized === canonical ? current : canonical;
  }); }, [canonical, multiline, separator]);
  const props = { className: "input mt-1 w-full py-2", disabled, value: raw,
    onChange: (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
      setRaw(event.target.value);
      onChange(event.target.value.split(multiline ? "\n" : ",").map(v => v.trim()).filter(Boolean));
    } };
  return <label className="block text-xs font-medium">{label}{multiline ? <textarea {...props} rows={4} /> : <input {...props} />}</label>;
}

export function RuleConfigFields({ type, config, disabled, patch }: Props) {
  const { t } = useTranslation("documentChecks");
  const label = (key: string) => t(`ruleFields.${key}` as never, { defaultValue: key });
  const optionLabel = (value: string) => t(`ruleValues.${value}` as never, { defaultValue: value });
  const number = (key: string, data = config, update = patch, optional = false) => <label key={key} className="block text-xs font-medium">
    {label(key)}<input type="number" step="any" disabled={disabled} className="input mt-1 w-full py-2"
      placeholder={optional ? t("notChecked") : undefined} value={String(data[key] ?? "")}
      onChange={e => update({ [key]: e.target.value === "" ? null : Number(e.target.value) })} />
  </label>;
  const text = (key: string) => <label key={key} className="block text-xs font-medium">{label(key)}<input disabled={disabled}
    className="input mt-1 w-full py-2" value={String(config[key] ?? "")} onChange={e => patch({ [key]: e.target.value })} /></label>;
  const flag = (key: string) => <label key={key} className="flex items-center gap-2 text-sm"><input type="checkbox" disabled={disabled}
    checked={Boolean(config[key])} onChange={e => patch({ [key]: e.target.checked })} />{label(key)}</label>;
  const choice = (key: string, values: string[], data = config, update = patch, optional = false) => <label key={key} className="block text-xs font-medium">
    {label(key)}<select disabled={disabled} className="input mt-1 w-full py-2" value={String(data[key] ?? "")}
      onChange={e => update({ [key]: e.target.value || null })}>
      {optional && <option value="">{t("notChecked")}</option>}{values.map(value => <option key={value} value={value}>{optionLabel(value)}</option>)}
    </select></label>;
  const list = (key: string, data = config, update = patch, optional = false, multiline = false) =>
    <ListField key={key} label={label(key) + (optional ? ` · ${t("optionalField")}` : "")} value={data[key]} disabled={disabled} multiline={multiline}
      onChange={value => update({ [key]: optional && !value.length ? null : value })} />;
  let fields;
  if (type === "PAGE_FORMAT_MARGINS") {
    const margins = (config.margins ?? {}) as Config;
    fields = <>{choice("page_size", ["A4", "LETTER", "LEGAL", "CUSTOM"], config, value => patch({ ...value,
      width_mm: value.page_size === "CUSTOM" ? 210 : null, height_mm: value.page_size === "CUSTOM" ? 297 : null }))}
      {choice("orientation", ["PORTRAIT", "LANDSCAPE"])}
      {config.page_size === "CUSTOM" && ["width_mm", "height_mm"].map(key => number(key))}
      {["top_mm", "right_mm", "bottom_mm", "left_mm"].map(key => number(key, margins, value => patch({ margins: { ...margins, ...value } })))}
    </>;
  } else if (type === "FONTS_SIZES") {
    fields = <>{list("allowed_fonts")}{number("min_size_pt")}{number("max_size_pt")}</>;
  } else if (type === "PARAGRAPH_SPACING_INDENTS") {
    fields = <>{choice("alignment", ALIGNMENTS, config, patch, true)}{SPACING.map(key => number(key))}</>;
  } else if (type === "HEADINGS") {
    const levels = (config.levels ?? []) as Config[];
    return <div className="mt-4 space-y-3">
      {flag("require_numbering")}<p className="text-xs text-[var(--color-muted)]">{t("numberingNote")}</p>
      {levels.map((level, index) => {
        const update = (value: Config) => patch({ levels: levels.map((item, i) => i === index ? { ...item, ...value } : item) });
        return <details key={String(level.level)} open className="rounded-lg border border-[var(--color-border)] p-3">
          <summary className="cursor-pointer text-sm font-bold">{t(`paragraphTypes.HEADING_${level.level}` as never)}</summary>
          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
            {list("allowed_fonts", level, update, true)}
            {["min_size_pt", "max_size_pt"].map(key => number(key, level, update))}
            {choice("alignment", ALIGNMENTS, level, update, true)}
            <label className="block text-xs font-medium">{label("bold")}<select disabled={disabled} className="input mt-1 w-full py-2"
              value={level.bold == null ? "" : String(level.bold)} onChange={e => update({ bold: e.target.value === "" ? null : e.target.value === "true" })}>
              <option value="">{t("notChecked")}</option><option value="true">{t("boldRequired")}</option><option value="false">{t("regularRequired")}</option>
            </select></label>
            {SPACING.map(key => number(key, level, update, true))}
          </div>
          {!disabled && levels.length > 1 && <button type="button" className="mt-3 text-xs font-semibold text-[var(--color-danger-500)]"
            onClick={() => patch({ levels: levels.filter((_, i) => i !== index) })}>{t("removeLevel")}</button>}
        </details>;
      })}
      {!disabled && levels.length < 6 && <button type="button" className="btn btn-secondary w-full" onClick={() => {
        const level = [1, 2, 3, 4, 5, 6].find(i => !levels.some(item => item.level === i))!;
        patch({ levels: [...levels, defaultHeadingLevel(level)].sort((a, b) => Number(a.level) - Number(b.level)) });
      }}>{t("addLevel")}</button>}
    </div>;
  } else if (type === "TABLES") {
    fields = <>{flag("require_header_row")}{flag("require_caption")}{choice("caption_position", ["ABOVE", "BELOW"])}
      <fieldset><legend className="text-xs font-medium">{label("allowed_alignments")}</legend>{ALIGNMENTS.slice(0, 3).map(value => <label key={value} className="mt-1 flex gap-2 text-sm">
        <input type="checkbox" disabled={disabled} checked={Array.isArray(config.allowed_alignments) && config.allowed_alignments.includes(value)} onChange={e => {
          const values = (config.allowed_alignments ?? []) as string[];
          patch({ allowed_alignments: e.target.checked ? [...values, value] : values.filter(v => v !== value) });
        }} />{optionLabel(value)}</label>)}</fieldset></>;
  } else if (type === "FIGURE_CAPTIONS") {
    fields = <>{flag("required")}{text("prefix")}{choice("position", ["ABOVE", "BELOW"])}{choice("numbering", ["ARABIC", "ROMAN", "NONE"])}</>;
  } else if (type === "REFERENCES") {
    fields = <>{choice("style", ["APA", "MLA", "CHICAGO", "GOST", "IEEE", "CUSTOM"], config, value => patch({ ...value,
      custom_style_name: value.style === "CUSTOM" ? "Custom" : null }))}{config.style === "CUSTOM" && text("custom_style_name")}
      {number("minimum_count")}{flag("require_in_text_citations")}</>;
  } else if (type === "REQUIRED_SECTIONS") {
    fields = <>{list("sections", config, patch, false, true)}{flag("case_sensitive")}</>;
  } else {
    fields = <>{list("languages")}{flag("ignore_uppercase")}{flag("ignore_urls")}</>;
  }
  return <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">{fields}</div>;
}
