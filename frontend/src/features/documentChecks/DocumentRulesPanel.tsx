import { useTranslation } from "react-i18next";
import type { CheckRule, CheckRuleType, DocumentSettings, ParagraphClassification, ParagraphType } from "../../types/api";
import { RuleConfigFields } from "./RuleConfigFields";
import { defaultConfig, EXECUTABLE_RULE_TYPES, RULE_TYPES } from "./ruleConfig";

type Props = {
  draft: DocumentSettings;
  disabled: boolean;
  onChange: (draft: DocumentSettings) => void;
  paragraphs: ParagraphClassification[];
  selectedParagraph: { index: number; text: string } | null;
};

export function DocumentRulesPanel({ draft, disabled, onChange, paragraphs, selectedParagraph }: Props) {
  const { t } = useTranslation("documentChecks");
  const setRules = (rules: CheckRule[]) => onChange({ ...draft, rules });
  const update = (index: number, value: CheckRule) => setRules(draft.rules.map((rule, i) => i === index ? value : rule));
  const paragraph = paragraphs.find(p => p.paragraph_index === selectedParagraph?.index);
  const manualType = selectedParagraph ? draft.paragraph_overrides[String(selectedParagraph.index)] : undefined;
  const effectiveType = manualType ?? paragraph?.automatic_type;
  return <div className="space-y-4">
    <p className="text-xs text-[var(--color-muted)]">{t("documentRulesHint")}</p>
    <section className="rounded-xl border border-[var(--color-brand-200)] bg-[var(--color-brand-50)] p-3">
      <h3 className="text-sm font-bold">{t("paragraphClassification")}</h3>
      <p className="mt-1 text-xs">{t("paragraphSelectionHint")}</p>
      {selectedParagraph && <div className="mt-3 space-y-2">
        <p className="text-xs font-semibold">{t("findingParagraph", { number: selectedParagraph.index })}</p>
        <p className="line-clamp-3 break-words text-xs">«{selectedParagraph.text}»</p>
        {effectiveType && <p className="text-sm font-semibold">{t(`paragraphTypes.${effectiveType}`)} · {t(manualType ? "classificationManual" : "classificationAuto")}</p>}
        {paragraph?.excluded && <p className="text-xs text-amber-900">{t("classificationExcluded")}</p>}
        <label className="block text-xs font-medium">{t("paragraphType")}<select disabled={disabled || !paragraph} className="input mt-1 w-full py-2"
          value={manualType ?? "AUTO"} onChange={e => {
            const overrides = { ...draft.paragraph_overrides };
            if (e.target.value === "AUTO") delete overrides[String(selectedParagraph.index)];
            else overrides[String(selectedParagraph.index)] = e.target.value as ParagraphType;
            onChange({ ...draft, paragraph_overrides: overrides });
          }}>
          <option value="AUTO">{t("classificationAuto")}{paragraph ? `: ${t(`paragraphTypes.${paragraph.automatic_type}`)}` : ""}</option>
          {(["BODY", "HEADING_1", "HEADING_2", "HEADING_3", "HEADING_4", "HEADING_5", "HEADING_6"] as ParagraphType[]).map(kind => <option key={kind} value={kind}>{t(`paragraphTypes.${kind}`)}</option>)}
        </select></label>
      </div>}
      <p className="mt-3 text-xs text-[var(--color-muted)]">{t("classificationLimitations")}</p>
    </section>
    {draft.rules.map((rule, index) => <details key={index} open className="rounded-xl border border-[var(--color-border)] p-3">
      <summary className="cursor-pointer text-sm font-bold">{t(`ruleTypes.${rule.rule_type}`)}
        {(rule.rule_type === "FONTS_SIZES" || rule.rule_type === "PARAGRAPH_SPACING_INDENTS") && <span className="block text-xs font-normal">{t("paragraphTypes.BODY")}</span>}
      </summary>
      {!EXECUTABLE_RULE_TYPES.has(rule.rule_type) && <p className="mt-2 rounded-lg bg-amber-50 p-2 text-xs text-amber-900">{t("ruleNotExecuted")}</p>}
      <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
        <label className="flex gap-2 text-xs"><input type="checkbox" disabled={disabled} checked={rule.enabled} onChange={e => update(index, { ...rule, enabled: e.target.checked })} />{t("enabled")}</label>
        <label className="text-xs">{t("severity")}<select className="input ml-1 py-1" disabled={disabled} value={rule.severity} onChange={e => update(index, { ...rule, severity: e.target.value as CheckRule["severity"] })}>
          {(["INFO", "WARNING", "ERROR"] as const).map(value => <option key={value} value={value}>{t(`severities.${value}`)}</option>)}
        </select></label>
      </div>
      <label className="mt-3 block text-xs">{t("category")}<input className="input mt-1 w-full py-2" disabled={disabled} value={rule.category} maxLength={100} onChange={e => update(index, { ...rule, category: e.target.value })} /></label>
      <RuleConfigFields type={rule.rule_type} config={rule.config} disabled={disabled} patch={value => update(index, { ...rule, config: { ...rule.config, ...value } })} />
      <button type="button" disabled={disabled} className="mt-3 text-xs font-semibold text-[var(--color-danger-500)]" onClick={() => setRules(draft.rules.filter((_, i) => i !== index).map((r, i) => ({ ...r, sort_order: i })))}>{t("removeRule")}</button>
    </details>)}
    <label className="block text-sm font-medium">{t("addRule")}<select className="input mt-1 w-full" disabled={disabled || draft.rules.length >= 201} value="" onChange={e => {
      const type = e.target.value as CheckRuleType;
      setRules([...draft.rules, { rule_type: type, category: "formatting", severity: "ERROR", enabled: true,
        sort_order: Math.max(-1, ...draft.rules.map(rule => rule.sort_order)) + 1, config_schema_version: 1, config: defaultConfig(type) }]);
    }}><option value="" disabled>{t("selectRuleType")}</option>{RULE_TYPES.map(type => <option key={type} value={type}>{t(`ruleTypes.${type}`)}</option>)}</select></label>
  </div>;
}
