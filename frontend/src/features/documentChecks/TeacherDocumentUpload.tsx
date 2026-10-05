import { useRef } from "react";
import { DocumentArrowUpIcon } from "@heroicons/react/24/outline";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ErrorState, LoadingState } from "../../components/ui/StateViews";
import { usePublishedProfileOptions } from "./reviewGroupApi";
import { useUploadTeacherDocumentSubmission } from "./submissionApi";

export function TeacherDocumentUpload({ groupId }: { groupId?: string }) {
  const { t } = useTranslation(["documentChecks", "common"]);
  const profiles = usePublishedProfileOptions();
  const upload = useUploadTeacherDocumentSubmission();
  const uploadKey = useRef<string | null>(null);
  const publishedVersions = (profiles.data?.items ?? []).flatMap((profile) =>
    profile.versions.filter((version) => version.state === "PUBLISHED" && version.executable_rule_count > 0).map((version) => ({
      id: version.id,
      label: `${profile.name} · ${t("version", { number: version.version_number })}`,
    })),
  );

  return (
      <section className="section-panel mb-7 overflow-hidden" aria-labelledby="upload-heading">
        <div className="grid lg:grid-cols-[280px_minmax(0,1fr)]">
          <div className="border-b border-[var(--color-border)] bg-[#f8f7f3] p-5 lg:border-b-0 lg:border-r lg:p-6">
            <span className="flex size-10 items-center justify-center rounded-[7px] border border-[var(--color-border)] bg-white text-[var(--color-brand-600)]"><DocumentArrowUpIcon className="size-5" aria-hidden="true" /></span>
            <h2 id="upload-heading" className="mt-4 text-base font-bold text-[var(--color-ink)]">{t("uploadForCheck")}</h2>
            <p className="mt-1 text-sm leading-6 text-[var(--color-muted)]">{t(groupId ? "reviewGroups.groupUploadHint" : "teacherUploadHint")}</p>
            <p className="mt-5 border-l-2 border-[var(--color-brand-500)] pl-3 text-xs leading-5 text-[var(--color-muted)]">{t("firstPagePolicy")}</p>
          </div>
          <div className="p-5 lg:p-6">
            {upload.isError && <div className="mb-4"><ErrorState compact error={upload.error} /></div>}
            {profiles.isLoading && <LoadingState label={t("common:loading")} />}
            {profiles.isError && <ErrorState compact error={profiles.error} onRetry={() => void profiles.refetch()} />}
            {!profiles.isError && !profiles.isLoading && !publishedVersions.length && <p className="mb-4 rounded-[7px] border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">{t("publishedProfileNeeded")} <Link className="font-semibold underline" to="/check-profiles">{t("profiles")}</Link></p>}
            <form onChange={() => { uploadKey.current = null; upload.reset(); }} onSubmit={(event) => {
              event.preventDefault();
              const form = event.currentTarget;
              const file = (form.elements.namedItem("file") as HTMLInputElement | null)?.files?.[0];
              const profileVersionId = (form.elements.namedItem("profile_version_id") as HTMLSelectElement | null)?.value;
              if (!file || !profileVersionId) return;
              const studentLabel = (form.elements.namedItem("student_label") as HTMLInputElement | null)?.value;
              const disclosure = (form.elements.namedItem("plagiarism_source_disclosure_allowed") as HTMLInputElement | null)?.checked ?? false;
              uploadKey.current ??= crypto.randomUUID();
              upload.mutate({
                file,
                groupId,
                workTitle: (form.elements.namedItem("work_title") as HTMLInputElement | null)?.value,
                workType: (form.elements.namedItem("work_type") as HTMLSelectElement | null)?.value as "COURSEWORK" | "REPORT" | undefined,
                profileVersionId,
                studentLabel,
                plagiarismSourceDisclosureAllowed: disclosure,
                idempotencyKey: uploadKey.current,
              }, { onSuccess: () => { form.reset(); uploadKey.current = null; } });
            }}><fieldset disabled={upload.isPending} className="grid gap-4 lg:grid-cols-2">
              <label className="text-sm font-semibold text-[var(--color-ink-soft)]">{t("chooseProfile")}<select name="profile_version_id" className="input mt-1.5 w-full" required><option value="">{t("choosePublishedVersion")}</option>{publishedVersions.map((version) => <option key={version.id} value={version.id}>{version.label}</option>)}</select></label>
              <label className="text-sm font-semibold text-[var(--color-ink-soft)]">{t(groupId ? "reviewGroups.student" : "studentLabel")}<input name="student_label" required={!!groupId} className="input mt-1.5 w-full" maxLength={255} placeholder={t(groupId ? "reviewGroups.studentPlaceholder" : "studentLabelPlaceholder")} /></label>
              {groupId && <>
                <label className="text-sm font-semibold">{t("reviewGroups.workTitle")}<input name="work_title" required maxLength={255} className="input mt-1.5 w-full" /></label>
                <label className="text-sm font-semibold">{t("reviewGroups.workType")}<select name="work_type" required className="input mt-1.5 w-full"><option value="COURSEWORK">{t("reviewGroups.coursework")}</option><option value="REPORT">{t("reviewGroups.report")}</option></select></label>
              </>}
              <label className="text-sm font-semibold text-[var(--color-ink-soft)] lg:col-span-2">{t("chooseDocx")}<span className="mt-1.5 block rounded-[7px] border border-dashed border-[#b9b9b3] bg-[#faf9f6] p-3"><input name="file" className="block w-full text-sm text-[var(--color-ink-soft)] file:mr-3 file:rounded-[5px] file:border-0 file:bg-[var(--color-brand-700)] file:px-3 file:py-2 file:text-sm file:font-semibold file:text-white" required type="file" accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document" /></span></label>
              <label className="flex items-start gap-2.5 text-sm text-[var(--color-ink-soft)] lg:col-span-2"><input name="plagiarism_source_disclosure_allowed" className="mt-1 size-4 accent-[var(--color-brand-700)]" type="checkbox" /><span><strong className="font-semibold text-[var(--color-ink)]">{t("shareSimilaritySource")}</strong><span className="mt-1 block text-xs leading-5 text-[var(--color-muted)]">{t("shareSimilaritySourceHint")}</span></span></label>
              <div className="flex flex-col gap-3 border-t border-[var(--color-border)] pt-4 sm:flex-row sm:items-center sm:justify-between lg:col-span-2"><p className="text-xs text-[var(--color-muted)]">{t("docxOnlyHint")}</p><button type="submit" className="btn btn-primary sm:min-w-40" disabled={upload.isPending || !publishedVersions.length}>{upload.isPending ? t("uploading") : t("startCheck")}</button></div>
            </fieldset></form>
          </div>
        </div>
      </section>
  );
}
