import { useState, type ComponentType, type SVGProps } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  ArrowRightStartOnRectangleIcon,
  Bars3Icon,
  ClipboardDocumentCheckIcon,
  ClipboardDocumentListIcon,
  DocumentTextIcon,
  ShieldCheckIcon,
  Squares2X2Icon,
  UserCircleIcon,
  UsersIcon,
  XMarkIcon,
} from "@heroicons/react/24/outline";
import { useAuth } from "../features/auth/useAuth";
import { BrandMark } from "../components/BrandMark";
import { NotificationBell } from "../components/NotificationBell";
import { OrganizationSwitcher } from "../components/OrganizationSwitcher";
import { LanguageSwitcher } from "../components/LanguageSwitcher";

type HeroIcon = ComponentType<SVGProps<SVGSVGElement>>;
type NavigationItem = { to: string; label: string; icon: HeroIcon };
type NavigationSection = { label: string; items: NavigationItem[] };

export function AppShell() {
  const { user, logout } = useAuth();
  const { t } = useTranslation(["common", "groups", "templates", "reports", "editor", "admin", "audit", "auth", "documentChecks", "disciplines"]);
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);

  if (!user) return null;

  const documentCheckEnabled = user.features?.document_check_enabled ?? true;
  const legacyDocumentEditorEnabled = user.features?.legacy_document_editor_enabled ?? true;
  const teacherWorkflowNav: NavigationItem[] = documentCheckEnabled
    ? [
        { to: "/review-groups", label: t("documentChecks:reviewGroups.title"), icon: UsersIcon },
        { to: "/document-checks", label: t("documentChecks:directChecks"), icon: ClipboardDocumentCheckIcon },
        { to: "/check-profiles", label: t("documentChecks:profiles"), icon: ClipboardDocumentCheckIcon },
      ]
    : [];
  const teacherAcademicNav: NavigationItem[] = [
    { to: "/disciplines", label: t("disciplines:title"), icon: DocumentTextIcon },
    { to: "/groups", label: t("groups:myGroups"), icon: UsersIcon },
    ...(legacyDocumentEditorEnabled
      ? [{ to: "/templates", label: t("templates:templates"), icon: DocumentTextIcon }]
      : []),
  ];
  const navSections: NavigationSection[] = user.role === "TEACHER"
    ? [
        { label: t("common:workflows"), items: teacherWorkflowNav },
        { label: t("common:academicManagement"), items: teacherAcademicNav },
      ]
    : user.role === "STUDENT"
      ? [
          { label: t("common:workflows"), items: [{ to: "/reports", label: t("reports:myReports"), icon: ClipboardDocumentListIcon }] },
          { label: t("common:accountAndAccess"), items: [{ to: "/profile", label: t("admin:profile"), icon: UserCircleIcon }] },
        ]
      : [{
          label: t("common:accountAndAccess"),
          items: [
            { to: "/admin", label: t("admin:administration"), icon: Squares2X2Icon },
            ...(user.role === "SUPER_ADMIN" ? [{ to: "/audit", label: t("audit:auditLog"), icon: ShieldCheckIcon }] : []),
          ],
        }];

  const closeMobile = () => setMobileOpen(false);
  const pageTitle = (pathname: string) => {
    if (pathname.startsWith("/disciplines")) return t("disciplines:title");
    if (pathname.startsWith("/review-groups")) return t("documentChecks:reviewGroups.title");
    if (pathname === "/document-checks") return t("documentChecks:directChecks");
    if (pathname.startsWith("/document-checks/")) return t("documentChecks:documentReview");
    if (pathname.includes("/check-profiles/")) return t("documentChecks:ruleConfiguration");
    if (pathname === "/check-profiles") return t("documentChecks:profiles");
    if (pathname.includes("/templates/")) return t("templates:templateEditor");
    if (pathname === "/templates") return t("templates:reportTemplates");
    if (pathname.includes("/groups/") && pathname.includes("/reports/")) return t("reports:reportReview");
    if (pathname.includes("/groups/")) return t("groups:group");
    if (pathname === "/groups") return t("groups:myGroups");
    if (pathname.includes("/reports/") && pathname.endsWith("/edit")) return t("reports:reportEditor");
    if (pathname === "/reports") return t("reports:myReports");
    if (pathname === "/profile") return t("admin:profile");
    if (pathname === "/admin") return t("admin:adminPanel");
    if (pathname === "/audit") return t("audit:auditLog");
    return t("common:appName");
  };

  const sideContent = (
    <>
      <div className="flex h-[82px] items-center justify-between border-b border-[var(--color-border)] px-5">
        <BrandMark showPrinciple />
        <button type="button" onClick={closeMobile} className="icon-button md:hidden" aria-label={t("common:closeMenu")}>
          <XMarkIcon className="size-5" />
        </button>
      </div>
      <nav className="flex-1 overflow-y-auto px-3 py-5" aria-label={t("common:workspace")}>
        {navSections.filter((section) => section.items.length > 0).map((section, index) => (
          <div key={section.label} className={index > 0 ? "mt-6" : ""}>
            <p className="px-3 pb-2 text-[10px] font-bold uppercase tracking-[0.13em] text-[var(--color-muted)]">{section.label}</p>
            <div className="space-y-0.5">
              {section.items.map((item) => {
                const NavIcon = item.icon;
                return (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    onClick={closeMobile}
                    className={({ isActive }) => `group relative flex min-h-10 items-center gap-3 rounded-[6px] px-3 py-2 text-sm font-semibold transition-colors ${isActive ? "bg-[var(--color-brand-50)] text-[var(--color-brand-700)] before:absolute before:inset-y-2 before:left-0 before:w-0.5 before:bg-[var(--color-brand-600)]" : "text-[var(--color-ink-soft)] hover:bg-[var(--color-surface)] hover:text-[var(--color-ink)]"}`}
                  >
                    <NavIcon className="size-[18px]" aria-hidden="true" />
                    <span className="truncate">{item.label}</span>
                  </NavLink>
                );
              })}
            </div>
          </div>
        ))}
      </nav>
      <div className="border-t border-[var(--color-border)] p-3">
        <div className="rounded-[7px] bg-[var(--color-surface)] p-3">
          <div className="flex min-w-0 items-center gap-2.5">
            <div className="flex size-9 shrink-0 items-center justify-center rounded-[6px] border border-[var(--color-border)] bg-white text-sm font-bold text-[var(--color-brand-700)]">{user.full_name.slice(0, 1).toUpperCase()}</div>
            <div className="min-w-0"><p className="truncate text-sm font-semibold text-[var(--color-ink)]">{user.full_name}</p><p className="truncate text-xs text-[var(--color-muted)]">{user.email}</p></div>
          </div>
          <button onClick={() => void logout()} className="mt-3 flex w-full items-center gap-2 rounded-[5px] px-2 py-1.5 text-xs font-semibold text-[var(--color-ink-soft)] transition-colors hover:bg-white hover:text-[var(--color-danger-500)]">
            <ArrowRightStartOnRectangleIcon className="size-4" />{t("auth:signOut")}
          </button>
        </div>
      </div>
    </>
  );

  return (
    <div className="min-h-screen bg-[var(--color-surface)] md:flex">
      {mobileOpen && <button type="button" aria-label={t("common:closeMenu")} onClick={closeMobile} className="fixed inset-0 z-40 bg-[var(--color-ink)]/40 md:hidden" />}
      <aside className={`fixed inset-y-0 left-0 z-50 flex w-[284px] flex-col border-r border-[var(--color-border)] bg-[var(--color-card)] shadow-[var(--shadow-float)] transition-transform duration-200 md:sticky md:top-0 md:h-screen md:w-[248px] md:translate-x-0 md:shadow-none ${mobileOpen ? "translate-x-0" : "-translate-x-full"}`}>{sideContent}</aside>
      <main className="min-w-0 flex-1">
        <header className="sticky top-0 z-30 flex h-[64px] items-center justify-between border-b border-[var(--color-border)] bg-white px-4 sm:px-6 lg:px-8">
          <div className="flex min-w-0 items-center gap-3">
            <button type="button" onClick={() => setMobileOpen(true)} className="icon-button -ml-2 md:hidden" aria-label={t("common:openMenu")}><Bars3Icon className="size-6" /></button>
            <div className="hidden min-w-0 sm:block"><p className="text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--color-muted)]">{t("common:workspace")}</p><p className="truncate text-base font-semibold tracking-[-0.01em] text-[var(--color-ink)] sm:text-lg">{pageTitle(location.pathname)}</p></div>
          </div>
          <div className="flex items-center gap-1 sm:gap-2">
            <LanguageSwitcher /><OrganizationSwitcher /><NotificationBell />
            <div className="hidden h-7 w-px bg-[var(--color-border)] lg:block" />
            <div className="hidden items-center gap-2 pl-1 lg:flex"><div className="flex size-8 items-center justify-center rounded-[6px] border border-[var(--color-border)] bg-[var(--color-surface)] text-xs font-bold text-[var(--color-brand-700)]">{user.full_name.slice(0, 1).toUpperCase()}</div><span className="max-w-36 truncate text-sm font-medium text-[var(--color-ink-soft)]">{user.full_name}</span></div>
          </div>
        </header>
        <div className="mx-auto max-w-[1480px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8"><Outlet /></div>
      </main>
    </div>
  );
}
