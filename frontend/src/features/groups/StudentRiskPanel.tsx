import { useState } from "react";
import { useTranslation } from "react-i18next";
import { StatusBadge } from "../../components/StatusBadge";
import { ErrorState } from "../../components/ui/StateViews";
import { useLocaleFormatters } from "../../i18n/formatters";
import type { StudentRiskItem, StudentRiskLevel } from "../../types/api";
import { useGroupStudentRisk } from "./api";

const LEVEL_STYLE: Record<StudentRiskLevel, string> = {
  RED: "bg-[var(--color-danger-50)] text-[var(--color-danger-500)]",
  YELLOW: "bg-[var(--color-amber-50)] text-[var(--color-amber-500)]",
  GREEN: "bg-[var(--color-success-50)] text-[var(--color-success-500)]",
};

const LEVEL_KEY = { RED: "red", YELLOW: "yellow", GREEN: "green" } as const;

/** Colour is never the only signal: every level also carries a text label. */
function RiskBadge({ level }: { level: StudentRiskLevel }) {
  const { t } = useTranslation("groups");
  const label = t(`studentRisk.${LEVEL_KEY[level]}`);
  return (
    <span data-risk-level={level} className={`inline-flex items-center gap-1.5 rounded-[5px] border border-current/15 px-2.5 py-1 text-xs font-semibold ${LEVEL_STYLE[level]}`}>
      <span aria-hidden="true" className="size-2 rounded-full bg-current" />
      {label}
    </span>
  );
}

function RiskRow({ item }: { item: StudentRiskItem }) {
  const { t } = useTranslation("groups");
  const { formatDate, formatNumber } = useLocaleFormatters();
  return (
    <tr>
      <td className="px-5 py-3 font-medium">{item.student_name}</td>
      <td className="px-5 py-3">{item.internship_title}</td>
      <td className="px-5 py-3"><StatusBadge status={item.report_status} /></td>
      <td className="px-5 py-3">{item.completion_percent === null ? t("studentRisk.noCompletion") : `${formatNumber(item.completion_percent)}%`}</td>
      <td className="px-5 py-3">{item.days_since_activity === 0 ? t("studentRisk.idleToday") : t("studentRisk.idleDays", { days: item.days_since_activity })}</td>
      <td className="px-5 py-3">{formatDate(item.deadline)}</td>
      <td className="px-5 py-3">
        <RiskBadge level={item.level} />
        {item.reasons.length > 0 && (
          <ul className="mt-1.5 list-disc pl-4 text-xs text-[var(--color-muted)]">
            {item.reasons.map((reason) => <li key={reason}>{t(`studentRisk.reasons.${reason}`)}</li>)}
          </ul>
        )}
      </td>
    </tr>
  );
}

export function StudentRiskPanel({ groupId }: { groupId: string }) {
  const { t } = useTranslation("groups");
  const { formatNumber } = useLocaleFormatters();
  const query = useGroupStudentRisk(groupId);
  const [onlyAttention, setOnlyAttention] = useState(true);

  if (query.isError) {
    return <div className="mb-6"><ErrorState compact error={query.error} message={t("studentRisk.loadError")} onRetry={() => void query.refetch()} /></div>;
  }
  const risk = query.data;
  if (!risk || risk.items.length === 0) return null;

  const needAttention = risk.red + risk.yellow;
  const visible = onlyAttention ? risk.items.filter((item) => item.level !== "GREEN") : risk.items;
  const counters: Array<[StudentRiskLevel, number]> = [["RED", risk.red], ["YELLOW", risk.yellow], ["GREEN", risk.green]];

  return (
    <section className="section-panel mb-6" aria-labelledby="student-risk-title">
      <div className="flex flex-wrap items-start justify-between gap-3 px-5 py-4">
        <div>
          <h2 id="student-risk-title" className="text-base font-semibold">{t("studentRisk.title")}</h2>
          <p className="mt-1 text-sm text-[var(--color-muted)]">{t("studentRisk.hint")}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2" aria-label={t("studentRisk.title")}>
          {counters.map(([level, count]) => (
            <span key={level} className="inline-flex items-center gap-2 text-sm"><RiskBadge level={level} /><strong>{formatNumber(count)}</strong></span>
          ))}
        </div>
      </div>
      <label className="flex items-center gap-2 border-t border-[var(--color-border)] px-5 py-3 text-sm">
        <input type="checkbox" checked={onlyAttention} onChange={(event) => setOnlyAttention(event.target.checked)} />
        {t("studentRisk.onlyAttention")}
      </label>
      {needAttention === 0 && onlyAttention ? (
        <p className="border-t border-[var(--color-border)] px-5 py-4 text-sm text-[var(--color-muted)]" role="status">{t("studentRisk.allOnTrack")}</p>
      ) : (
        <div className="table-frame">
          <table className="table-base min-w-[760px]">
            <thead>
              <tr>
                <th className="px-5 py-3 font-medium">{t("studentRisk.student")}</th>
                <th className="px-5 py-3 font-medium">{t("studentRisk.practice")}</th>
                <th className="px-5 py-3 font-medium">{t("studentRisk.status")}</th>
                <th className="px-5 py-3 font-medium">{t("studentRisk.written")}</th>
                <th className="px-5 py-3 font-medium">{t("studentRisk.idle")}</th>
                <th className="px-5 py-3 font-medium">{t("studentRisk.deadline")}</th>
                <th className="px-5 py-3 font-medium">{t("studentRisk.risk")}</th>
              </tr>
            </thead>
            <tbody>{visible.map((item) => <RiskRow key={item.report_id} item={item} />)}</tbody>
          </table>
        </div>
      )}
    </section>
  );
}
