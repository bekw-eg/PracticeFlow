import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { fetchOrganizationsPage } from "../features/auth/api";
import { useAuth } from "../features/auth/useAuth";
import { showToast } from "../lib/toast";
import { BuildingOffice2Icon, ChevronDownIcon } from "@heroicons/react/24/outline";
import { ErrorState } from "./ui/StateViews";
import { PaginationControls } from "./ui/PaginationControls";

export function OrganizationSwitcher() {
  const { user, switchOrganization } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [offset, setOffset] = useState(0);
  const { data: page, isFetching, isError, error, refetch } = useQuery({ queryKey: ["auth", "organizations", { offset }], queryFn: () => fetchOrganizationsPage(offset) });
  const organizations = page?.items ?? [];
  if (!isError && page && page.total < 2) return null;
  const chooseOrganization = async (organization: typeof organizations[number]) => {
    const challenge = await switchOrganization(organization.id);
    setOpen(false);
    if (challenge) {
      sessionStorage.setItem("practiceflow_mfa_challenge", JSON.stringify(challenge));
      navigate("/mfa", { state: { challenge } });
      return;
    }
    showToast(`Организация: ${organization.name}`);
  };
  return <div className="relative"><button onClick={() => setOpen((value) => !value)} className="inline-flex max-w-44 items-center gap-1.5 rounded-xl border border-[var(--color-border)] bg-white px-2.5 py-2 text-xs font-semibold text-[var(--color-ink-soft)] shadow-[0_1px_2px_rgba(15,27,45,0.03)] hover:bg-[var(--color-surface)]" aria-label="Сменить организацию" aria-expanded={open}><BuildingOffice2Icon className="size-4 shrink-0" /><span className="hidden truncate md:inline">Организация</span><ChevronDownIcon className="size-3.5 shrink-0" /></button>{open && <div className="absolute right-0 top-full z-50 mt-2 w-64 overflow-hidden rounded-2xl border border-[var(--color-border)] bg-white shadow-[var(--shadow-float)]">{isError ? <div className="p-3"><ErrorState compact error={error} onRetry={() => void refetch()} /></div> : <>{organizations.map((organization) => <button key={organization.id} disabled={organization.id === user?.organization_id} onClick={() => void chooseOrganization(organization).catch(() => undefined)} className="block w-full border-b border-[var(--color-border)] px-4 py-3 text-left transition-colors last:border-0 hover:bg-[var(--color-surface)] disabled:bg-[var(--color-brand-50)]"><span className="block text-sm font-semibold text-[var(--color-ink)]">{organization.name}</span><span className="mt-0.5 block text-xs text-[var(--color-muted)]">{organization.slug} · {organization.role}</span></button>)}{page && <div className="px-3 pb-3"><PaginationControls pagination={page} onPageChange={setOffset} isFetching={isFetching} label="Организации" /></div>}</>}</div>}</div>;
}
