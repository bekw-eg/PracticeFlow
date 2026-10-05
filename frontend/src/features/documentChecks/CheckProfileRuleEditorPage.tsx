import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeftIcon, PlusIcon, TrashIcon } from "@heroicons/react/24/outline";
import { useTranslation } from "react-i18next";
import { ErrorState, LoadingState } from "../../components/ui/StateViews";
import { StatusBadge } from "../../components/StatusBadge";
import { showToast } from "../../lib/toast";
import type { CheckRule, CheckRuleType } from "../../types/api";
import { useCheckProfileVersion, useProfileVersionAction, useReplaceCheckRules } from "./api";

import { RULE_TYPES, EXECUTABLE_RULE_TYPES, defaultConfig } from "./ruleConfig";
import { RuleConfigFields } from "./RuleConfigFields";

export function CheckProfileRuleEditorPage() {
  const { profileId, versionId } = useParams<{ profileId: string; versionId: string }>();
  return <CheckProfileRuleEditor key={`${profileId}/${versionId}`} profileId={profileId!} versionId={versionId!} />;
}

function CheckProfileRuleEditor({ profileId, versionId }: { profileId: string; versionId: string }) {
  const { t } = useTranslation(["documentChecks", "common"]);
  const navigate = useNavigate();
  const query = useCheckProfileVersion(profileId, versionId);
  const [rules, setRules] = useState<CheckRule[]>([]);
  const [dirty, setDirty] = useState(false);
  const initialized = useRef(false);
  const save = useReplaceCheckRules(profileId, versionId);
  const publish = useProfileVersionAction(profileId, versionId, "publish");
  const retire = useProfileVersionAction(profileId, versionId, "retire");
  useEffect(() => {
    // A background refetch must not erase edits or restore a removed rule.
    if (query.data?.rules && !initialized.current) {
      setRules(query.data.rules);
      initialized.current = true;
    }
  }, [query.data]);
  if (query.isLoading) return <LoadingState label={t("loadingVersion")} />;
  if (query.isError || !query.data) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  const editable = query.data.state === "DRAFT" || query.data.state === "PUBLISHED";
  const busy = save.isPending || publish.isPending || retire.isPending;
  const canPublish = rules.some((rule) => rule.enabled && EXECUTABLE_RULE_TYPES.has(rule.rule_type));
  const changeRules = (change: (current: CheckRule[]) => CheckRule[]) => {
    setRules(change);
    setDirty(true);
  };
  const updateRule = (index: number, next: CheckRule) => changeRules((current) => current.map((rule, i) => i === index ? next : rule));
  const saveCurrent = async () => {
    try {
      const version = await save.mutateAsync(rules);
      setRules(version.rules ?? []);
      setDirty(false);
      showToast(t(version.id !== versionId && version.state === "DRAFT" ? "rulesSavedAsDraft" : "rulesSaved"));
      if (version.id !== versionId) navigate(`/check-profiles/${profileId}/versions/${version.id}`, { replace: true });
    } catch {
      // Keep local edits available after a failed save.
    }
  };
  const publishCurrent = async () => {
    try {
      const version = await save.mutateAsync(rules);
      setRules(version.rules ?? []);
      setDirty(false);
      await publish.mutateAsync();
      showToast(t("versionPublished"));
    } catch {
      // API errors are presented by the shared request error handler.
    }
  };
  return <div>
    <Link to="/check-profiles" className="inline-flex items-center gap-1.5 text-sm font-semibold text-[var(--color-muted)]"><ArrowLeftIcon className="size-4" />{t("profiles")}</Link>
    <header className="mt-4 mb-6 flex flex-wrap items-start justify-between gap-4">
      <div><p className="page-kicker">{t("ruleConfiguration")}</p><h1 className="page-title mt-1">{t("version", { number: query.data.version_number })}</h1><p className="page-description">{t("configurationOnly")}</p></div>
      <div className="flex flex-wrap gap-2">
        <StatusBadge status={query.data.state} />
        {editable && <button className="btn btn-primary" disabled={busy || !dirty} onClick={() => void saveCurrent()}>{t("common:save")}</button>}
        {query.data.state === "DRAFT" && <button className="btn btn-secondary" disabled={!canPublish || busy} onClick={() => void publishCurrent()}>{t("saveAndPublish")}</button>}
        {query.data.state === "PUBLISHED" && <button className="btn btn-danger" disabled={busy || dirty} onClick={() => retire.mutate(undefined, { onSuccess: () => showToast(t("versionRetired")) })}>{t("retireVersion")}</button>}
      </div>
    </header>
    {query.data.state === "PUBLISHED" && <p className="mb-4 rounded-xl bg-[var(--color-brand-50)] p-3 text-sm">{t("publishedRulesEditable")}</p>}
    {dirty && <div className="mb-4 flex flex-wrap items-center justify-between gap-2 rounded-xl bg-amber-50 p-3 text-sm text-amber-900"><span>{t("rulesUnsavedChanges")}</span><button className="font-semibold underline" disabled={busy} onClick={() => { setRules(query.data.rules ?? []); setDirty(false); }}>{t("discardRuleChanges")}</button></div>}
    {(save.isError || publish.isError || retire.isError) && <div className="mb-4"><ErrorState compact error={save.error ?? publish.error ?? retire.error} /></div>}
    {!canPublish && <p className="mb-4 rounded-xl bg-amber-50 p-3 text-sm font-semibold text-amber-900">{t("activeRuleRequired")}</p>}
    {!rules.length && <p className="card p-5 text-sm text-[var(--color-muted)]">{t("emptyRuleList")}</p>}
    <div className="space-y-4">{rules.map((rule, index) => <RuleCard key={rule.id ?? index} rule={rule} disabled={!editable || busy} onChange={(next) => updateRule(index, next)} onRemove={() => changeRules((current) => current.filter((_, i) => i !== index).map((item, i) => ({ ...item, sort_order: i })))} />)}</div>
    {editable && <div className="mt-5 flex flex-wrap gap-2"><button className="btn btn-secondary" disabled={busy} onClick={() => changeRules((current) => [...current, { rule_type: "PAGE_FORMAT_MARGINS", category: "formatting", severity: "ERROR", enabled: true, sort_order: current.length, config_schema_version: 1, config: defaultConfig("PAGE_FORMAT_MARGINS") }])}><PlusIcon className="size-4" />{t("addRule")}</button><button className="btn btn-primary" disabled={busy || !dirty} onClick={() => void saveCurrent()}>{t("common:save")}</button></div>}
  </div>;
}

function RuleCard({ rule, disabled, onChange, onRemove }: { rule: CheckRule; disabled: boolean; onChange: (rule: CheckRule) => void; onRemove: () => void }) {
  const { t } = useTranslation(["documentChecks", "common"]);
  const patchConfig = (patch: Record<string, unknown>) => onChange({ ...rule, config: { ...rule.config, ...patch } });
  return <section className="card p-5"><div className="grid gap-3 md:grid-cols-4"><label className="text-sm font-medium">{t("ruleType")}<select disabled={disabled} className="input mt-1 w-full" value={rule.rule_type} onChange={(event) => { const type = event.target.value as CheckRuleType; onChange({ ...rule, rule_type: type, config: defaultConfig(type) }); }}>{RULE_TYPES.map((type) => <option key={type} value={type}>{t(`ruleTypes.${type}` as never)}</option>)}</select></label><label className="text-sm font-medium">{t("category")}<input disabled={disabled} className="input mt-1 w-full" value={rule.category} onChange={(event) => onChange({ ...rule, category: event.target.value })} /></label><label className="text-sm font-medium">{t("severity")}<select disabled={disabled} className="input mt-1 w-full" value={rule.severity} onChange={(event) => onChange({ ...rule, severity: event.target.value as CheckRule["severity"] })}><option value="INFO">INFO</option><option value="WARNING">WARNING</option><option value="ERROR">ERROR</option></select></label><label className="flex items-end gap-2 pb-3 text-sm font-medium"><input disabled={disabled} type="checkbox" checked={rule.enabled} onChange={(event) => onChange({ ...rule, enabled: event.target.checked })} />{t("enabled")}</label></div><RuleConfigFields type={rule.rule_type} config={rule.config} disabled={disabled} patch={patchConfig} />{!disabled && <button className="mt-4 inline-flex items-center gap-1 text-sm font-semibold text-[var(--color-danger-500)]" onClick={onRemove}><TrashIcon className="size-4" />{t("removeRule")}</button>}</section>;
}

