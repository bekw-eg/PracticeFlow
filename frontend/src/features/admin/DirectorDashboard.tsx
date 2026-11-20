import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { EmptyState, ErrorState, LoadingState } from "../../components/ui/StateViews";
import { useLocaleFormatters } from "../../i18n/formatters";
import { api } from "../../lib/api";
import type { DirectorDashboard } from "../../types/api";

function Metric({ label, value, note }: {
  label: string;
  value: number;
  note: string;
}) {
  const { formatNumber } = useLocaleFormatters();
  return (
    <article className="min-w-0 border-l-2 border-l-transparent bg-[var(--color-card)] p-4 sm:p-5">
      <p className="text-sm text-[var(--color-muted)]">{label}</p>
      <p className="mt-2 font-display text-3xl font-bold tracking-[-0.035em] text-[var(--color-ink)]">
        {formatNumber(value)}
      </p>
      <p className="mt-1 text-xs text-[var(--color-muted)]">{note}</p>
    </article>
  );
}

function SectionLink({ to, children }: { to: string; children: string }) {
  return (
    <Link to={to} className="btn btn-secondary px-3 py-2 text-sm text-[var(--color-brand-700)]">
      {children}
    </Link>
  );
}

export function DirectorDashboardPage() {
  const { t } = useTranslation(["admin", "common"]);
  const { formatNumber } = useLocaleFormatters();
  const dashboard = useQuery({
    queryKey: ["director", "dashboard"],
    queryFn: async () => (await api.get<DirectorDashboard>("/director/dashboard")).data,
  });

  if (dashboard.isLoading) return <LoadingState label={t("directorLoading")} />;
  if (dashboard.isError) {
    return (
      <ErrorState
        error={dashboard.error}
        message={t("directorLoadError")}
        onRetry={() => void dashboard.refetch()}
      />
    );
  }
  if (!dashboard.data) return <EmptyState title={t("directorUnavailable")} />;

  const data = dashboard.data;
  const hasOperationalData = data.groups.length > 0 || data.teacher_loads.length > 0 || data.students_count > 0;
  return (
    <div>
      <header className="mb-6 border-b border-[var(--color-border)] border-l-4 border-l-[var(--color-brand-600)] bg-white px-5 py-5 sm:px-6">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--color-brand-600)]">
          {t("directorDashboardKicker")}
        </p>
        <div className="mt-1 flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="font-display text-2xl font-bold tracking-[-0.025em] text-[var(--color-ink)]">
              {data.organization.name}
            </h1>
            <p className="mt-1 max-w-2xl text-sm text-[var(--color-muted)]">
              {t("directorDashboardDescription")}
            </p>
          </div>
          <span className="rounded-[5px] border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1.5 text-xs font-semibold text-[var(--color-ink-soft)]">
            {t("common:roles.DIRECTOR")}
          </span>
        </div>
      </header>

      {!hasOperationalData ? (
        <EmptyState title={t("directorEmptyTitle")} description={t("directorEmptyDescription")} />
      ) : (
        <>
          <section className="section-panel grid overflow-hidden sm:grid-cols-3 sm:divide-x sm:divide-y-0" aria-label={t("directorMetrics")}>
            <Metric label={t("groupsMetric")} value={data.groups_count} note={t("groupsMetricNote")} />
            <Metric label={t("studentsMetric")} value={data.students_count} note={t("studentsMetricNote")} />
            <Metric label={t("teachersMetric")} value={data.teachers_count} note={t("teachersMetricNote")} />
          </section>

          <section className="section-panel mt-6 p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="font-display text-xl font-bold text-[var(--color-ink)]">{t("directorGroupsTitle")}</h2>
                <p className="mt-1 text-sm text-[var(--color-muted)]">{t("directorGroupsDescription")}</p>
              </div>
              <SectionLink to="/admin?view=management&tab=groups">{t("directorOpenGroups")}</SectionLink>
            </div>
            {data.groups.length === 0 ? <p className="mt-4 text-sm text-[var(--color-muted)]">{t("directorNoGroups")}</p> : (
              <div className="mt-4 overflow-x-auto">
                <table className="table-base min-w-[480px]">
                  <thead className="text-xs uppercase tracking-wide text-[var(--color-muted)]">
                    <tr><th className="pb-2 pr-4">{t("groupsTab")}</th><th className="pb-2 pr-4">{t("academicYear")}</th><th className="pb-2">{t("studentsMetric")}</th></tr>
                  </thead>
                  <tbody>
                    {data.groups.map((group) => (
                      <tr key={group.id} className="border-t border-[var(--color-border)] text-[var(--color-ink-soft)]">
                        <td className="py-3 pr-4 font-medium text-[var(--color-ink)]">{group.name}</td>
                        <td className="py-3 pr-4">{group.academic_year ?? t("academicYearMissing")}</td>
                        <td className="py-3">{formatNumber(group.student_count)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="section-panel mt-6 p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="font-display text-xl font-bold text-[var(--color-ink)]">{t("directorTeacherLoadTitle")}</h2>
                <p className="mt-1 text-sm text-[var(--color-muted)]">{t("directorTeacherLoadDescription")}</p>
              </div>
              <SectionLink to="/admin?view=management&tab=members">{t("directorOpenMembers")}</SectionLink>
            </div>
            {data.teacher_loads.length === 0 ? <p className="mt-4 text-sm text-[var(--color-muted)]">{t("directorNoTeachers")}</p> : (
              <div className="mt-4 overflow-x-auto">
                <table className="table-base min-w-[420px]">
                  <thead className="text-xs uppercase tracking-wide text-[var(--color-muted)]">
                    <tr><th className="pb-2 pr-4">{t("teachersMetric")}</th><th className="pb-2">{t("groupsMetric")}</th></tr>
                  </thead>
                  <tbody>
                    {data.teacher_loads.map((teacher) => (
                      <tr key={teacher.id} className="border-t border-[var(--color-border)] text-[var(--color-ink-soft)]">
                        <td className="py-3 pr-4 font-medium text-[var(--color-ink)]">{teacher.full_name}</td>
                        <td className="py-3">{formatNumber(teacher.groups_count)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}
