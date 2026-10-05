import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { DocumentMagnifyingGlassIcon, PlusIcon } from "@heroicons/react/24/outline";
import { useTranslation } from "react-i18next";
import { EmptyState, ErrorState, LoadingState } from "../../components/ui/StateViews";
import { PaginationControls } from "../../components/ui/PaginationControls";
import { StatusBadge } from "../../components/StatusBadge";
import { useCreateCheckProfile, useCreateCheckProfileVersion, useCheckProfiles } from "./api";

export function CheckProfilesPage() {
  const { t } = useTranslation(["documentChecks", "common"]);
  const [params, setParams] = useSearchParams();
  const offset = Math.max(0, Number(params.get("offset") ?? 0) || 0);
  const query = useCheckProfiles(offset);
  const createProfile = useCreateCheckProfile();
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  const changePage = (nextOffset: number) => {
    const next = new URLSearchParams(params);
    if (nextOffset) next.set("offset", String(nextOffset));
    else next.delete("offset");
    setParams(next);
  };

  return <div>
    <header className="mb-7 flex flex-wrap items-end justify-between gap-4 border-b border-[var(--color-border)] pb-6">
      <div><p className="page-kicker">{t("phaseOne")}</p><h1 className="page-title mt-1">{t("profiles")}</h1><p className="page-description">{t("profilesDescription")}</p></div>
      <button className="btn btn-primary" onClick={() => setCreating(true)}><PlusIcon className="size-4" />{t("newProfile")}</button>
    </header>
    {creating && <form className="section-panel mb-6 grid gap-3 p-5 md:grid-cols-[1fr_2fr_auto]" onSubmit={(event) => {
      event.preventDefault();
      createProfile.mutate({ name, description: description || undefined }, { onSuccess: () => { setName(""); setDescription(""); setCreating(false); } });
    }}>
      <label className="text-sm font-medium">{t("profileName")}<input className="input mt-1 w-full" required maxLength={255} value={name} onChange={(event) => setName(event.target.value)} /></label>
      <label className="text-sm font-medium">{t("description")}<input className="input mt-1 w-full" maxLength={5000} value={description} onChange={(event) => setDescription(event.target.value)} /></label>
      <div className="flex items-end gap-2"><button disabled={createProfile.isPending} className="btn btn-primary" type="submit">{t("common:create")}</button><button className="btn btn-ghost" type="button" onClick={() => setCreating(false)}>{t("common:cancel")}</button></div>
    </form>}
    {query.isLoading && <LoadingState label={t("loadingProfiles")} />}
    {query.isError && <ErrorState error={query.error} onRetry={() => void query.refetch()} />}
    {!query.isLoading && !query.isError && !query.data?.items.length && <EmptyState title={t("noProfiles")} description={t("noProfilesDescription")} />}
    {!!query.data?.items.length && <div className="section-panel divide-y divide-[var(--color-border)] overflow-hidden">{query.data.items.map((profile) => <ProfileCard key={profile.id} profile={profile} />)}</div>}
    {query.data && <PaginationControls pagination={query.data} onPageChange={changePage} isFetching={query.isFetching} label={t("profiles")} />}
  </div>;
}

function ProfileCard({ profile }: { profile: import("../../types/api").CheckProfile }) {
  const { t } = useTranslation(["documentChecks", "common"]);
  const createVersion = useCreateCheckProfileVersion(profile.id);
  const versions = [...profile.versions].sort((left, right) => right.version_number - left.version_number);
  const currentVersions = versions.filter((version) => version.state !== "RETIRED");
  const history = versions.filter((version) => version.state === "RETIRED");
  const versionLink = (version: (typeof profile.versions)[number]) => <Link key={version.id} className="inline-flex items-center gap-2 rounded-[5px] border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm font-semibold hover:border-[var(--color-brand-500)]" to={`/check-profiles/${profile.id}/versions/${version.id}`}><span>{t("version", { number: version.version_number })}</span><span className={version.executable_rule_count ? "text-[var(--color-muted)]" : "text-[var(--color-danger-500)]"}>{t("activeRules", { count: version.executable_rule_count })}</span><StatusBadge status={version.state} /></Link>;
  return <article className="bg-white p-5 sm:p-6">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="flex gap-3"><span className="flex size-10 items-center justify-center rounded-[7px] border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-brand-600)]"><DocumentMagnifyingGlassIcon className="size-5" /></span><div><h2 className="font-display font-bold text-[var(--color-ink)]">{profile.name}</h2>{profile.description && <p className="mt-1 text-sm text-[var(--color-muted)]">{profile.description}</p>}</div></div>
      <button className="btn btn-secondary px-3 py-2" disabled={createVersion.isPending} onClick={() => createVersion.mutate(undefined)}><PlusIcon className="size-4" />{t("newVersion")}</button>
    </div>
    <div className="mt-4 flex flex-wrap gap-2">{currentVersions.map(versionLink)}{!profile.versions.length && <span className="text-sm text-[var(--color-muted)]">{t("noVersions")}</span>}</div>
    {!!history.length && <details className="mt-4 text-sm text-[var(--color-muted)]"><summary className="cursor-pointer font-semibold">{t("versionHistory", { count: history.length })}</summary><div className="mt-3 flex flex-wrap gap-2">{history.map(versionLink)}</div></details>}
  </article>;
}
