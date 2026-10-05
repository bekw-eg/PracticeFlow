import { api } from "../lib/api";
import { exportErrorMessage } from "../lib/resourceErrorMessages";
import { DocumentArrowDownIcon } from "@heroicons/react/24/outline";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

function filenameFromHeader(contentDisposition: string | undefined, fallback: string) {
  const match = contentDisposition?.match(/filename="?([^";]+)"?/i);
  return match?.[1] ?? fallback;
}

type ExportFormat = "docx" | "pdf";
type ExportStatus = "queued" | "running" | "succeeded" | "failed" | "timed_out" | "cancelled";

type ActiveExport = {
  id: string;
  format: ExportFormat;
  status: ExportStatus;
  downloadUrl?: string;
};

async function download(downloadUrl: string, format: ExportFormat) {
  const response = await api.get(downloadUrl, { responseType: "blob" });
  const url = URL.createObjectURL(response.data);
  const link = document.createElement("a");
  link.href = url;
  link.download = filenameFromHeader(response.headers["content-disposition"], `report.${format}`);
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export function ExportButtons({ reportId, compact = false }: { reportId: string; compact?: boolean }) {
  const { t } = useTranslation("export");
  const [active, setActive] = useState<ActiveExport | null>(null);
  const [isStarting, setIsStarting] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const baseClass = compact
    ? "inline-flex items-center gap-1 rounded-lg border border-[var(--color-border)] px-2.5 py-1.5 text-xs font-semibold text-[var(--color-ink-soft)] hover:bg-[var(--color-surface)]"
    : "inline-flex items-center gap-1.5 rounded-xl border border-[var(--color-border)] bg-white px-3 py-2.5 text-sm font-semibold text-[var(--color-ink-soft)] shadow-[0_1px_2px_rgba(15,27,45,0.03)] hover:bg-[var(--color-surface)]";

  useEffect(() => {
    if (!active || active.status !== "queued" && active.status !== "running") return;
    let cancelled = false;
    let timeoutId: number | undefined;
    const poll = async () => {
      try {
        const response = await api.get(`/export-jobs/${active.id}`);
        if (cancelled) return;
        const job = response.data as { status: ExportStatus; download_url?: string };
        if (job.status === "succeeded") {
          setActive({ ...active, status: job.status, downloadUrl: job.download_url });
          return;
        }
        if (job.status === "failed" || job.status === "timed_out" || job.status === "cancelled") {
          setActive(null);
          setError(t("failed"));
          return;
        }
        timeoutId = window.setTimeout(() => void poll(), 1500);
      } catch (requestError) {
        if (!cancelled) {
          setActive(null);
          setError(exportErrorMessage(requestError));
        }
      }
    };
    void poll();
    return () => {
      cancelled = true;
      if (timeoutId !== undefined) window.clearTimeout(timeoutId);
    };
  }, [active, t]);

  const startExport = async (format: ExportFormat) => {
    if (active || isDownloading || isStarting) return;
    setIsStarting(true);
    setError(null);
    try {
      const response = await api.post(`/reports/${reportId}/exports/${format}`);
      const job = response.data as { job_id: string; status: ExportStatus };
      setActive({ id: job.job_id, format, status: job.status });
    } catch (requestError) {
      setError(exportErrorMessage(requestError));
    } finally {
      setIsStarting(false);
    }
  };

  const downloadReadyExport = async () => {
    if (!active?.downloadUrl || isDownloading) return;
    setIsDownloading(true);
    setError(null);
    try {
      await download(active.downloadUrl, active.format);
      setActive(null);
    } catch (requestError) {
      setError(exportErrorMessage(requestError));
    } finally {
      setIsDownloading(false);
    }
  };

  const preparing = active?.status === "queued" || active?.status === "running";
  const disabled = Boolean(active) || isDownloading || isStarting;

  return (
    <div>
      <div className="flex gap-2">
        <button type="button" disabled={disabled} onClick={() => void startExport("docx")} className={baseClass} aria-label={t("startFormat", { format: "DOCX" })}><DocumentArrowDownIcon className="size-4" aria-hidden="true" />DOCX</button>
        <button type="button" disabled={disabled} onClick={() => void startExport("pdf")} className={baseClass} aria-label={t("startFormat", { format: "PDF" })}><DocumentArrowDownIcon className="size-4" aria-hidden="true" />PDF</button>
        {active?.status === "succeeded" && active.downloadUrl && (
          <button type="button" disabled={isDownloading} onClick={() => void downloadReadyExport()} className={baseClass}>
            <DocumentArrowDownIcon className="size-4" aria-hidden="true" />{isDownloading ? t("downloading") : t("download", { format: active.format.toUpperCase() })}
          </button>
        )}
      </div>
      {preparing && <p role="status" className="mt-2 text-xs text-[var(--color-ink-soft)]">{t("preparing")}</p>}
      {error && <p role="alert" className="mt-2 text-xs text-[var(--color-danger-500)]">{error}</p>}
    </div>
  );
}
