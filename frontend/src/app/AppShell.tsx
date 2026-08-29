import { useState, type ComponentType, type SVGProps } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { Bars3Icon, ClipboardDocumentListIcon, DocumentTextIcon, UserCircleIcon, UsersIcon, XMarkIcon, ArrowRightStartOnRectangleIcon, Squares2X2Icon, ShieldCheckIcon } from "@heroicons/react/24/outline";
import { useAuth } from "../features/auth/useAuth";
import { NotificationBell } from "../components/NotificationBell";
import { OrganizationSwitcher } from "../components/OrganizationSwitcher";

type HeroIcon = ComponentType<SVGProps<SVGSVGElement>>;
type NavigationItem = { to: string; label: string; icon: HeroIcon };

const TEACHER_NAV: NavigationItem[] = [{ to: "/groups", label: "Мои группы", icon: UsersIcon }, { to: "/templates", label: "Шаблоны", icon: DocumentTextIcon }];
const STUDENT_NAV: NavigationItem[] = [{ to: "/reports", label: "Мои отчёты", icon: ClipboardDocumentListIcon }, { to: "/profile", label: "Мой профиль", icon: UserCircleIcon }];
const ADMIN_NAV: NavigationItem[] = [{ to: "/admin", label: "Управление", icon: Squares2X2Icon }];

function pageTitle(pathname: string) {
  if (pathname.includes("/templates/")) return "Редактор шаблона";
  if (pathname === "/templates") return "Шаблоны отчётов";
  if (pathname.includes("/groups/") && pathname.includes("/reports/")) return "Проверка отчёта";
  if (pathname.includes("/groups/")) return "Группа";
  if (pathname === "/groups") return "Мои группы";
  if (pathname.includes("/reports/") && pathname.endsWith("/edit")) return "Редактор отчёта";
  if (pathname === "/reports") return "Мои отчёты";
  if (pathname === "/profile") return "Мой профиль";
  if (pathname === "/admin") return "Панель управления";
  if (pathname === "/audit") return "Журнал аудита";
  return "PracticeFlow";
}

export function AppShell() {
  const { user, logout } = useAuth();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  if (!user) return null;
  const navItems = user.role === "TEACHER" ? TEACHER_NAV : user.role === "STUDENT" ? STUDENT_NAV : user.role === "SUPER_ADMIN" ? [...ADMIN_NAV, { to: "/audit", label: "Журнал аудита", icon: ShieldCheckIcon }] : ADMIN_NAV;
  const closeMobile = () => setMobileOpen(false);
  const sideContent = <><div className="flex h-[76px] items-center justify-between px-5"><div className="flex items-center gap-3"><div className="flex size-9 items-center justify-center rounded-xl bg-[var(--color-brand-500)] font-display text-base font-extrabold text-white shadow-[0_4px_12px_rgba(36,82,232,0.26)]">P</div><div><p className="font-display text-lg font-extrabold tracking-[-0.03em] text-[var(--color-ink)]">PracticeFlow</p><p className="text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--color-muted)]">University workspace</p></div></div><button type="button" onClick={closeMobile} className="icon-button md:hidden" aria-label="Закрыть меню"><XMarkIcon className="size-5" /></button></div><nav className="flex-1 space-y-1 px-3 py-3" aria-label="Основная навигация"><p className="px-3 pb-2 text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--color-muted)]">Рабочее пространство</p>{navItems.map((item) => { const NavIcon = item.icon; return <NavLink key={item.to} to={item.to} onClick={closeMobile} className={({ isActive }) => `group flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold transition-all ${isActive ? "bg-[var(--color-brand-50)] text-[var(--color-brand-700)] shadow-[inset_3px_0_0_var(--color-brand-500)]" : "text-[var(--color-ink-soft)] hover:bg-[var(--color-surface)] hover:text-[var(--color-ink)]"}`}><NavIcon className="size-5" aria-hidden="true" />{item.label}</NavLink>; })}</nav><div className="m-3 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3"><div className="flex min-w-0 items-center gap-2.5"><div className="flex size-9 shrink-0 items-center justify-center rounded-full bg-[var(--color-brand-100)] text-sm font-bold text-[var(--color-brand-700)]">{user.full_name.slice(0, 1).toUpperCase()}</div><div className="min-w-0"><p className="truncate text-sm font-bold text-[var(--color-ink)]">{user.full_name}</p><p className="truncate text-xs text-[var(--color-muted)]">{user.email}</p></div></div><button onClick={() => void logout()} className="mt-3 flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-xs font-semibold text-[var(--color-ink-soft)] transition-colors hover:bg-white hover:text-[var(--color-danger-500)]"><ArrowRightStartOnRectangleIcon className="size-4" />Выйти</button></div></>;
  return <div className="min-h-screen bg-[var(--color-surface)] md:flex">{mobileOpen && <button type="button" aria-label="Закрыть меню" onClick={closeMobile} className="fixed inset-0 z-40 bg-[var(--color-ink)]/35 backdrop-blur-[1px] md:hidden" />}<aside className={`fixed inset-y-0 left-0 z-50 flex w-[286px] flex-col border-r border-[var(--color-border)] bg-[var(--color-card)] shadow-[var(--shadow-float)] transition-transform duration-200 md:sticky md:top-0 md:h-screen md:w-[264px] md:translate-x-0 md:shadow-none ${mobileOpen ? "translate-x-0" : "-translate-x-full"}`}>{sideContent}</aside><main className="min-w-0 flex-1"><header className="sticky top-0 z-30 flex h-[68px] items-center justify-between border-b border-[var(--color-border)] bg-white/88 px-4 backdrop-blur-xl sm:px-6 lg:px-8"><div className="flex min-w-0 items-center gap-3"><button type="button" onClick={() => setMobileOpen(true)} className="icon-button -ml-2 md:hidden" aria-label="Открыть меню"><Bars3Icon className="size-6" /></button><div className="min-w-0"><p className="truncate font-display text-lg font-extrabold tracking-[-0.02em] text-[var(--color-ink)] sm:text-xl">{pageTitle(location.pathname)}</p><p className="hidden text-xs text-[var(--color-muted)] lg:block">PracticeFlow · цифровая практика</p></div></div><div className="flex items-center gap-1.5 sm:gap-2"><OrganizationSwitcher /><NotificationBell /><div className="hidden h-7 w-px bg-[var(--color-border)] sm:block" /><div className="hidden items-center gap-2 pl-1 sm:flex"><div className="flex size-8 items-center justify-center rounded-full bg-[var(--color-brand-50)] text-xs font-bold text-[var(--color-brand-700)]">{user.full_name.slice(0, 1).toUpperCase()}</div><span className="max-w-32 truncate text-sm font-semibold text-[var(--color-ink-soft)]">{user.full_name}</span></div></div></header><div className="mx-auto max-w-[1440px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8"><Outlet /></div></main></div>;
}
