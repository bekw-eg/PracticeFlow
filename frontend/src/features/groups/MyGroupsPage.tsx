import { Link, useSearchParams } from "react-router-dom";
import { GroupCodeChip } from "../../components/GroupCodeChip";
import { useMyGroups } from "./api";
import { ArrowRightIcon, UserGroupIcon } from "@heroicons/react/24/outline";
import { EmptyState, ErrorState, LoadingState } from "../../components/ui/StateViews";
import { PaginationControls } from "../../components/ui/PaginationControls";
import { useTranslation } from "react-i18next";
import { useLocaleFormatters } from "../../i18n/formatters";

export function MyGroupsPage() {
  const { t } = useTranslation("groups");
  const { formatCount } = useLocaleFormatters();
  const [searchParams, setSearchParams] = useSearchParams();
  const offset = Math.max(0, Number(searchParams.get("offset") ?? "0") || 0);
  const { data: page, isLoading, isFetching, isError, error, refetch } = useMyGroups(offset);
  const groups = page?.items ?? [];
  const changePage = (nextOffset: number) => {
    const next = new URLSearchParams(searchParams);
    if (nextOffset === 0) next.delete("offset");
    else next.set("offset", String(nextOffset));
    setSearchParams(next);
  };

  return (
    <div>
      <header className="mb-7 border-b border-[var(--color-border)] pb-6">
        <p className="page-kicker">{t("teacher")}</p><h1 className="page-title mt-1">{t("myGroups")}</h1><p className="page-description">{t("teacherWorkspaceDescription")}</p>
      </header>

      {isLoading && <LoadingState label={t("loadingGroups")} />}
      {isError && <ErrorState error={error} onRetry={() => void refetch()} />}

      {!isLoading && !isError && groups?.length === 0 && (
        <EmptyState title={t("groupsNotAssigned")} description={t("groupsNotAssignedDescription")} />
      )}

      {groups.length > 0 && <div className="section-panel divide-y divide-[var(--color-border)] overflow-hidden">
        {!isError && groups?.map((group) => (
          <Link
            key={group.id}
            to={`/groups/${group.id}`}
            className="group grid gap-4 bg-white p-5 transition-colors hover:bg-[#faf9f6] sm:grid-cols-[minmax(180px,1fr)_minmax(140px,0.55fr)_auto] sm:items-center"
          >
            <div className="min-w-0">
              <GroupCodeChip code={group.name} />
              {group.academic_year && <p className="mt-2 text-xs text-[var(--color-muted)]">{group.academic_year}</p>}
            </div>
            <div className="flex items-center gap-2 text-sm text-[var(--color-ink-soft)]"><UserGroupIcon className="size-4 text-[var(--color-muted)]" />
              {formatCount(group.student_count, (values) => t("studentCount", values))}
            </div>
            <span className="inline-flex items-center gap-1.5 text-sm font-semibold text-[var(--color-brand-600)] group-hover:text-[var(--color-brand-700)]">{t("openGroup")}<ArrowRightIcon className="size-4 transition-transform group-hover:translate-x-0.5" /></span>
          </Link>
        ))}
      </div>}
      {!isError && page && <PaginationControls pagination={page} onPageChange={changePage} isFetching={isFetching} label={t("myGroups")} />}
    </div>
  );
}
