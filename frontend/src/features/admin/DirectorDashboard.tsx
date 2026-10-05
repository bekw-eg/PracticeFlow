import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { EmptyState, ErrorState, LoadingState } from "../../components/ui/StateViews";
import { useLocaleFormatters } from "../../i18n/formatters";
import { api } from "../../lib/api";
import type { DirectorDashboard, ReportStatus } from "../../types/api";

const REPORT_STATUS_KEYS: Record<
  ReportStatus,
  | "common:statuses.DRAFT"
  | "common:statuses.SUBMITTED"
  | "common:statuses.UNDER_REVIEW"
  | "common:statuses.REVISION_REQUIRED"
  | "common:statuses.APPROVED"
  | "common:statuses.LOCKED"
> = {
  DRAFT: "common:statuses.DRAFT",
  SUBMITTED: "common:statuses.SUBMITTED",
  UNDER_REVIEW: "common:statuses.UNDER_REVIEW",
  REVISION_REQUIRED: "common:statuses.REVISION_REQUIRED",
  APPROVED: "common:statuses.APPROVED",
  LOCKED: "common:statuses.LOCKED",
};

function formatCalendarDate(value: string, formatDate: (value: string) => string) {
  // Date-only API fields represent an academic calendar day, not midnight UTC.
  return formatDate(`${value}T12:00:00`);
}

function Metric({ label, value, note, tone = "default" }: {
  label: string;
  value: number;
  note: string;
  tone?: "default" | "danger";
}) {
  const { formatNumber } = useLocaleFormatters();
  return (
    <article className={`min-w-0 border-l-2 p-4 sm:p-5 ${tone === "danger" ? "border-l-[var(--color-danger-500)] bg-[var(--color-danger-50)]" : "border-l-transparent bg-[var(--color-card)]"}`}>
      <p className="text-sm text-[var(--color-muted)]">{label}</p>
      <p className={`mt-2 font-display text-3xl font-bold tracking-[-0.035em] ${tone === "danger" ? "text-[var(--color-danger-500)]" : "text-[var(--color-ink)]"}`}>
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
  const { formatDate, formatNumber } = useLocaleFormatters();
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
  const hasOperationalData = data.groups.length > 0 || data.internships.length > 0 || data.reports_count > 0 || data.teacher_loads.length > 0;
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
          <section className="section-panel grid overflow-hidden sm:grid-cols-2 sm:divide-x sm:divide-y-0 xl:grid-cols-5" aria-label={t("directorMetrics")}>
            <Metric label={t("groupsMetric")} value={data.groups_count} note={t("groupsMetricNote")} />
            <Metric label={t("directorInternshipsMetric")} value={data.internships_count} note={t("directorInternshipsMetricNote")} />
            <Metric label={t("reportsMetric")} value={data.reports_count} note={t("reportsMetricNote")} />
            <Metric label={t("directorOverdueMetric")} value={data.overdue_reports_count} note={t("directorOverdueMetricNote")} tone="danger" />
            <Metric label={t("teachersMetric")} value={data.teacher_loads.length} note={t("teachersMetricNote")} />
          </section>

          <section className="section-panel mt-6 p-5">
            <h2 className="font-display text-xl font-bold text-[var(--color-ink)]">{t("directorReportStatuses")}</h2>
            <p className="mt-1 text-sm text-[var(--color-muted)]">{t("directorReportStatusesDescription")}</p>
            {data.report_statuses.length === 0 ? (
              <p className="mt-4 text-sm text-[var(--color-muted)]">{t("directorNoReports")}</p>
            ) : (
              <div className="mt-4 flex flex-wrap gap-2">
                {data.report_statuses.map((item) => (
                  <span key={item.status} className="rounded-[5px] border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm text-[var(--color-ink-soft)]">
                    {t(REPORT_STATUS_KEYS[item.status])}: <strong className="text-[var(--color-ink)]">{formatNumber(item.count)}</strong>
                  </span>
                ))}
              </div>
            )}
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
                <table className="table-base min-w-[640px]">
                  <thead className="text-xs uppercase tracking-wide text-[var(--color-muted)]">
                    <tr><th className="pb-2 pr-4">{t("groupsTab")}</th><th className="pb-2 pr-4">{t("academicYear")}</th><th className="pb-2 pr-4">{t("studentsMetric")}</th><th className="pb-2 pr-4">{t("directorInternshipsMetric")}</th><th className="pb-2 pr-4">{t("reportsMetric")}</th><th className="pb-2">{t("directorOverdueMetric")}</th></tr>
                  </thead>
                  <tbody>
                    {data.groups.map((group) => (
                      <tr key={group.id} className="border-t border-[var(--color-border)] text-[var(--color-ink-soft)]">
                        <td className="py-3 pr-4 font-medium text-[var(--color-ink)]">{group.name}</td>
                        <td className="py-3 pr-4">{group.academic_year ?? t("academicYearMissing")}</td>
                        <td className="py-3 pr-4">{formatNumber(group.student_count)}</td>
                        <td className="py-3 pr-4">{formatNumber(group.internships_count)}</td>
                        <td className="py-3 pr-4">{formatNumber(group.reports_count)}</td>
                        <td className="py-3 text-[var(--color-danger-500)]">{formatNumber(group.overdue_reports_count)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="section-panel mt-6 p-5">
            <h2 className="font-display text-xl font-bold text-[var(--color-ink)]">{t("directorInternshipsTitle")}</h2>
            <p className="mt-1 text-sm text-[var(--color-muted)]">{t("directorInternshipsDescription")}</p>
            {data.internships.length === 0 ? <p className="mt-4 text-sm text-[var(--color-muted)]">{t("directorNoInternships")}</p> : (
              <div className="mt-4 overflow-x-auto">
                <table className="table-base min-w-[700px]">
                  <thead className="text-xs uppercase tracking-wide text-[var(--color-muted)]">
                    <tr><th className="pb-2 pr-4">{t("directorInternshipsMetric")}</th><th className="pb-2 pr-4">{t("groupsTab")}</th><th className="pb-2 pr-4">{t("common:statuses.PUBLISHED")}</th><th className="pb-2 pr-4">{t("directorDeadline")}</th><th className="pb-2 pr-4">{t("reportsMetric")}</th><th className="pb-2">{t("directorOverdueMetric")}</th></tr>
                  </thead>
                  <tbody>
                    {data.internships.map((internship) => (
                      <tr key={internship.id} className="border-t border-[var(--color-border)] text-[var(--color-ink-soft)]">
                        <td className="py-3 pr-4 font-medium text-[var(--color-ink)]">{internship.title}</td>
                        <td className="py-3 pr-4">{internship.group_name}</td>
                        <td className="py-3 pr-4">{t(`common:statuses.${internship.status}`)}</td>
                        <td className="py-3 pr-4">{formatCalendarDate(internship.deadline, formatDate)}</td>
                        <td className="py-3 pr-4">{formatNumber(internship.reports_count)}</td>
                        <td className="py-3 text-[var(--color-danger-500)]">{formatNumber(internship.overdue_reports_count)}</td>
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
                <table className="table-base min-w-[600px]">
                  <thead className="text-xs uppercase tracking-wide text-[var(--color-muted)]">
                    <tr><th className="pb-2 pr-4">{t("teachersMetric")}</th><th className="pb-2 pr-4">{t("groupsMetric")}</th><th className="pb-2 pr-4">{t("directorActiveInternships")}</th><th className="pb-2">{t("directorAwaitingReview")}</th></tr>
                  </thead>
                  <tbody>
                    {data.teacher_loads.map((teacher) => (
                      <tr key={teacher.id} className="border-t border-[var(--color-border)] text-[var(--color-ink-soft)]">
                        <td className="py-3 pr-4 font-medium text-[var(--color-ink)]">{teacher.full_name}</td>
                        <td className="py-3 pr-4">{formatNumber(teacher.groups_count)}</td>
                        <td className="py-3 pr-4">{formatNumber(teacher.active_internships_count)}</td>
                        <td className="py-3">{formatNumber(teacher.reports_to_review_count)}</td>
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
