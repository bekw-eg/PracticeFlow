import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "./useAuth";
import { ArrowRightIcon, BuildingLibraryIcon, LockClosedIcon, UserIcon } from "@heroicons/react/24/outline";
import { getApiErrorPresentation } from "../../lib/apiError";

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [organizationSlug, setOrganizationSlug] = useState("demo-university");
  const [error, setError] = useState<unknown>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

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
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-[var(--color-surface)] px-4 py-10"><div className="absolute -left-32 top-0 size-96 rounded-full bg-[var(--color-brand-100)]/60 blur-3xl" /><div className="absolute -bottom-40 right-0 size-[32rem] rounded-full bg-[var(--color-brand-50)] blur-3xl" />
      <div className="relative w-full max-w-[440px]">
        <div className="mb-8 text-center"><div className="mx-auto flex size-14 items-center justify-center rounded-2xl bg-[var(--color-brand-500)] font-display text-xl font-extrabold text-white shadow-[0_12px_28px_rgba(36,82,232,0.28)]">P</div>
          <span className="mt-4 block font-display text-3xl font-extrabold tracking-[-0.04em] text-[var(--color-ink)]">PracticeFlow</span>
          <p className="mt-2 text-sm text-[var(--color-muted)]">Платформа управления университетской практикой</p>
        </div>

        <form onSubmit={handleSubmit} className="card p-6 sm:p-7">
          <div className="mb-6"><p className="page-kicker">Добро пожаловать</p><h1 className="mt-1 font-display text-xl font-bold text-[var(--color-ink)]">Войдите в рабочее пространство</h1></div>
          <div className="space-y-4">
            <Field label="Организация" icon={BuildingLibraryIcon}>
              <input
                value={organizationSlug}
                onChange={(e) => setOrganizationSlug(e.target.value)}
                className="input"
                placeholder="demo-university"
                required
              />
            </Field>
            <Field label="Email" icon={UserIcon}>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="input"
                placeholder="teacher@demo.edu"
                required
              />
            </Field>
            <Field label="Пароль" icon={LockClosedIcon}>
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
            {isSubmitting ? "Вход…" : <>Войти<ArrowRightIcon className="size-4" /></>}
          </button>
        </form>
      </div>
    </div>
  );
}

function LoginError({ error }: { error: unknown }) {
  const presentation = getApiErrorPresentation(error);
  const message = presentation.status === 401 || presentation.status === 403
    ? "Неверный email, пароль или организация."
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
