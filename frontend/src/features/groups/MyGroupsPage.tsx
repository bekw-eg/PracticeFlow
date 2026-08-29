import { Link, useSearchParams } from "react-router-dom";
import { GroupCodeChip } from "../../components/GroupCodeChip";
import { useMyGroups } from "./api";
import { ArrowRightIcon, UserGroupIcon } from "@heroicons/react/24/outline";
import { EmptyState, ErrorState, LoadingState } from "../../components/ui/StateViews";
import { PaginationControls } from "../../components/ui/PaginationControls";

function studentWord(count: number): string {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod10 === 1 && mod100 !== 11) return "студент";
  if ([2, 3, 4].includes(mod10) && ![12, 13, 14].includes(mod100)) return "студента";
  return "студентов";
}

export function MyGroupsPage() {
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
      <header className="mb-7">
        <p className="page-kicker">Преподаватель</p><h1 className="page-title mt-1">Мои группы</h1><p className="page-description">Ваше основное рабочее пространство — практика ведётся по группам.</p>
      </header>

      {isLoading && <LoadingState label="Загрузка групп…" />}
      {isError && <ErrorState error={error} onRetry={() => void refetch()} />}

      {!isLoading && !isError && groups?.length === 0 && (
        <EmptyState title="Группы ещё не назначены" description="Обратитесь к директору, чтобы получить доступ к группе и начать работу с практикой." />
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {!isError && groups?.map((group) => (
          <Link
            key={group.id}
            to={`/groups/${group.id}`}
            className="card group relative overflow-hidden p-5 transition-all hover:-translate-y-0.5 hover:border-[var(--color-brand-100)] hover:shadow-[var(--shadow-float)]"
          >
            <div className="flex items-start justify-between">
              <GroupCodeChip code={group.name} />
              {group.academic_year && <span className="text-xs text-[var(--color-muted)]">{group.academic_year}</span>}
            </div>
            <div className="mt-6 flex items-center gap-2 text-sm text-[var(--color-ink-soft)]"><UserGroupIcon className="size-4 text-[var(--color-muted)]" />
              {group.student_count} {studentWord(group.student_count)}
            </div>
            <span className="mt-5 inline-flex items-center gap-1.5 text-sm font-bold text-[var(--color-brand-500)] group-hover:text-[var(--color-brand-600)]">Открыть группу<ArrowRightIcon className="size-4 transition-transform group-hover:translate-x-1" /></span>
          </Link>
        ))}
      </div>
      {!isError && page && <PaginationControls pagination={page} onPageChange={changePage} isFetching={isFetching} label="Группы" />}
    </div>
  );
}
