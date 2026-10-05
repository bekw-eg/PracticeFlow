import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "./useAuth";
import { ArrowRightIcon, BuildingLibraryIcon, KeyIcon, LockClosedIcon, UserIcon, XMarkIcon } from "@heroicons/react/24/outline";
import { getApiErrorPresentation } from "../../lib/apiError";
import { useTranslation } from "react-i18next";
import { LanguageSwitcher } from "../../components/LanguageSwitcher";
import { api } from "../../lib/api";
import { BrandMark } from "../../components/BrandMark";

export function LoginPage() {
  const { t } = useTranslation(["auth", "common"]);
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [organizationSlug, setOrganizationSlug] = useState("demo-university");
  const [error, setError] = useState<unknown>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [accessDialogOpen, setAccessDialogOpen] = useState(false);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      const challenge = await login({ email, password, organization_slug: organizationSlug });
      if (challenge) {
        sessionStorage.setItem("practiceflow_mfa_challenge", JSON.stringify(challenge));
        navigate("/mfa", { state: { challenge } });
      } else {
        navigate("/");
      }
    } catch (requestError) {
      setError(requestError);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <main className="grid min-h-screen bg-[var(--color-surface)] lg:grid-cols-[minmax(320px,0.82fr)_minmax(520px,1.18fr)]">
      <section className="relative flex min-h-[190px] flex-col justify-between overflow-hidden bg-[var(--color-brand-700)] p-6 text-white sm:p-9 lg:min-h-screen lg:p-12" aria-label={t("common:appName")}>
        <BrandMark inverse showPrinciple />
        <div className="hidden max-w-lg lg:block">
          <div className="mb-8 h-px w-16 bg-white/45" />
          <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-white/65">{t("common:universityWorkspace")}</p>
          <p className="mt-4 max-w-md text-4xl font-semibold leading-[1.15] tracking-[-0.035em]">{t("auth:platformDescription")}</p>
          <p className="mt-6 text-base font-medium text-white/75">{t("common:brandPrinciple")}</p>
        </div>
        <div className="pointer-events-none absolute -bottom-16 -right-16 size-64 border border-white/10" aria-hidden="true"><div className="absolute inset-10 border border-white/10" /><div className="absolute inset-20 border border-white/10" /></div>
      </section>
      <section className="relative flex items-center justify-center px-4 py-8 sm:px-8 lg:py-12">
        <LanguageSwitcher className="absolute right-4 top-4 sm:right-7 sm:top-6" />
        <div className="w-full max-w-[460px]">
          <div className="mb-6 lg:hidden"><p className="text-sm text-[var(--color-muted)]">{t("auth:platformDescription")}</p></div>
          <form onSubmit={handleSubmit} className="card p-6 sm:p-8">
          <div className="mb-7 border-b border-[var(--color-border)] pb-5"><p className="page-kicker">{t("auth:welcome")}</p><h1 className="mt-1 text-2xl font-semibold tracking-[-0.025em] text-[var(--color-ink)]">{t("auth:signInHeading")}</h1></div>
          <div className="space-y-4">
            <Field label={t("auth:organization")} icon={BuildingLibraryIcon}>
              <input
                value={organizationSlug}
                onChange={(e) => setOrganizationSlug(e.target.value)}
                className="input"
                placeholder="demo-university"
                required
              />
            </Field>
            <Field label={t("auth:email")} icon={UserIcon}>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="input"
                placeholder="teacher@demo.edu"
                required
              />
            </Field>
            <Field label={t("auth:password")} icon={LockClosedIcon}>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="input"
                placeholder="••••••••"
                required
              />
            </Field>
          </div>

          {error !== null && <LoginError error={error} />}

          <button
            type="submit"
            disabled={isSubmitting}
            className="btn btn-primary mt-6 w-full"
          >
            {isSubmitting ? t("auth:signingIn") : <>{t("auth:signIn")}<ArrowRightIcon className="size-4" /></>}
          </button>
          <button type="button" onClick={() => setAccessDialogOpen(true)} className="mt-4 w-full text-sm font-semibold text-[var(--color-brand-600)] hover:text-[var(--color-brand-700)]">
            {t("auth:cantSignIn")} <span className="underline underline-offset-2">{t("auth:recoverAccess")}</span>
          </button>
          </form>
        </div>
      </section>
      {accessDialogOpen && <AccessRequestDialog initialEmail={email} initialOrganizationSlug={organizationSlug} onClose={() => setAccessDialogOpen(false)} />}
    </main>
  );
}

function AccessRequestDialog({ initialEmail, initialOrganizationSlug, onClose }: { initialEmail: string; initialOrganizationSlug: string; onClose: () => void }) {
  const { t } = useTranslation(["auth", "common"]);
  const [email, setEmail] = useState(initialEmail);
  const [organizationSlug, setOrganizationSlug] = useState(initialOrganizationSlug);
  const [state, setState] = useState<"idle" | "submitting" | "submitted" | "error">("idle");
  const [error, setError] = useState<unknown>(null);

  const requestAccess = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setState("submitting");
    try {
      await api.post("/auth/password-reset/request", { email, organization_slug: organizationSlug });
      setState("submitted");
    } catch (requestError) {
      setError(requestError);
      setState("error");
    }
  };

  const presentation = error !== null ? getApiErrorPresentation(error, "auth") : null;
  const errorMessage = presentation?.status === 429 ? t("auth:passwordResetRateLimited") : presentation?.description;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--color-ink)]/45 p-4" role="presentation">
      <section className="card w-full max-w-md p-6 sm:p-7" role="dialog" aria-modal="true" aria-labelledby="access-request-heading" aria-describedby="access-request-description">
        <div className="flex items-start justify-between gap-4"><div className="flex size-11 items-center justify-center rounded-xl bg-[var(--color-brand-50)] text-[var(--color-brand-600)]"><KeyIcon aria-hidden="true" className="size-6" /></div><button type="button" onClick={onClose} className="rounded-lg p-1.5 text-[var(--color-muted)] hover:bg-[var(--color-surface)] hover:text-[var(--color-ink)]" aria-label={t("auth:closeRecoveryDialog")}><XMarkIcon aria-hidden="true" className="size-5" /></button></div>
        <h2 id="access-request-heading" className="mt-4 font-display text-xl font-bold text-[var(--color-ink)]">{t("auth:recoverAccessHeading")}</h2>
        {state === "submitted" ? <div className="mt-4"><p className="rounded-xl bg-[var(--color-success-50)] px-3 py-2.5 text-sm leading-6 text-[var(--color-success-500)]" role="status">{t("auth:passwordResetRequestSent")}</p><p className="mt-4 text-sm leading-6 text-[var(--color-muted)]">{t("auth:contactAdministrator")}</p><button type="button" onClick={onClose} className="btn btn-primary mt-5 w-full">{t("auth:closeRecoveryDialog")}</button></div> : <form onSubmit={requestAccess} className="mt-4 space-y-4"><p id="access-request-description" className="text-sm leading-6 text-[var(--color-muted)]">{t("auth:recoverAccessDescription")}</p><label className="block"><span className="form-label flex items-center gap-1.5"><BuildingLibraryIcon aria-hidden="true" className="size-4" />{t("auth:organization")}</span><input value={organizationSlug} onChange={(event) => setOrganizationSlug(event.target.value)} className="input" required /></label><label className="block"><span className="form-label flex items-center gap-1.5"><UserIcon aria-hidden="true" className="size-4" />{t("auth:email")}</span><input type="email" value={email} onChange={(event) => setEmail(event.target.value)} className="input" required /></label><p className="rounded-xl bg-[var(--color-surface)] px-3 py-2.5 text-sm leading-6 text-[var(--color-muted)]">{t("auth:contactAdministrator")}</p>{state === "error" && <p className="rounded-xl bg-[var(--color-danger-50)] px-3 py-2.5 text-sm font-medium text-[var(--color-danger-500)]" role="alert">{errorMessage}</p>}<button disabled={state === "submitting"} className="btn btn-primary w-full">{state === "submitting" ? t("auth:sendingRecoveryInstructions") : t("auth:sendRecoveryInstructions")}</button></form>}
      </section>
    </div>
  );
}

function LoginError({ error }: { error: unknown }) {
  const { t } = useTranslation("auth");
  const presentation = getApiErrorPresentation(error, "auth");
  const message = presentation.status === 401 || presentation.status === 403
    ? t("invalidCredentials")
    : presentation.description;
  return <p className="mt-4 rounded-xl bg-[var(--color-danger-50)] px-3 py-2.5 text-sm font-medium text-[var(--color-danger-500)]" role="alert">{message}</p>;
}

function Field({ label, icon: Icon, children }: { label: string; icon: typeof BuildingLibraryIcon; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="form-label flex items-center gap-1.5"><Icon className="size-4 text-[var(--color-muted)]" />{label}</span>{children}
    </label>
  );
}
