import { Navigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../features/auth/useAuth";
import type { Role } from "../types/api";

export function ProtectedRoute({ children, allowedRoles }: { children: React.ReactNode; allowedRoles?: Role[] }) {
  const { user, isLoading } = useAuth();
  const { t } = useTranslation("common");

  if (isLoading) {
    return <div className="flex h-screen items-center justify-center text-[var(--color-muted)]">{t("loading")}</div>;
  }
  if (!user) {
    return <Navigate to="/login" replace />;
  }
  if (allowedRoles && !allowedRoles.includes(user.role)) {
    return <Navigate to="/" replace />;
  }
  return <>{children}</>;
}
