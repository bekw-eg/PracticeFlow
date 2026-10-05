import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { useAuth } from "../auth/useAuth";
import { UserOperations } from "./UserOperations";
import { GroupAssignments } from "./GroupAssignments";
import type {
  ManagementCatalog,
  ManagementGroup,
  ManagementMember,
  ManagementOverview,
  OrganizationOut,
  Role,
} from "../../types/api";
import { PlusIcon } from "@heroicons/react/24/outline";
import { ErrorState, LoadingState } from "../../components/ui/StateViews";
import { PaginationControls } from "../../components/ui/PaginationControls";
import {
  DEFAULT_PAGE_SIZE,
  fetchPage,
  type PaginationInfo,
} from "../../lib/pagination";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";
import { useLocaleFormatters } from "../../i18n/formatters";
import { DirectorDashboardPage } from "./DirectorDashboard";

type Tab =
  | "overview"
  | "members"
  | "user-operations"
  | "groups"
  | "assignments"
  | "catalog"
  | "organizations"
  | "mfa-recovery";
type RequestState = {
  isLoading: boolean;
  isError: boolean;
  error: unknown;
  refetch: () => Promise<unknown>;
};
type MfaRecoveryRequest = {
  id: string;
  user_id: string;
  user_email: string;
  user_name: string;
  expires_at: string;
  created_at: string;
};
const ROLE_TRANSLATION_KEYS: Record<
  Role,
  "roles.STUDENT" | "roles.TEACHER" | "roles.DIRECTOR" | "roles.SUPER_ADMIN"
> = {
  STUDENT: "roles.STUDENT",
  TEACHER: "roles.TEACHER",
  DIRECTOR: "roles.DIRECTOR",
  SUPER_ADMIN: "roles.SUPER_ADMIN",
};

function useManagementData(
  isSuperAdmin: boolean,
  memberOffset: number,
  memberSearch: string,
  groupOffset: number,
  organizationOffset: number,
) {
  const overview = useQuery({
    queryKey: ["management", "overview"],
    queryFn: async () =>
      (await api.get<ManagementOverview>("/management/overview")).data,
  });
  const members = useQuery({
    queryKey: ["management", "members", { memberOffset, memberSearch }],
    queryFn: () =>
      fetchPage<ManagementMember>("/management/members", {
        offset: memberOffset,
        limit: DEFAULT_PAGE_SIZE,
        q: memberSearch,
      }),
  });
  const groups = useQuery({
    queryKey: ["management", "groups", { groupOffset }],
    queryFn: () =>
      fetchPage<ManagementGroup>("/management/groups", {
        offset: groupOffset,
        limit: DEFAULT_PAGE_SIZE,
      }),
  });
  const catalog = useQuery({
    queryKey: ["management", "catalog"],
    queryFn: async () =>
      (await api.get<ManagementCatalog>("/management/catalog")).data,
  });
  const organizations = useQuery({
    queryKey: ["management", "organizations", { organizationOffset }],
    queryFn: () =>
      fetchPage<OrganizationOut>("/management/organizations", {
        offset: organizationOffset,
        limit: DEFAULT_PAGE_SIZE,
      }),
    enabled: isSuperAdmin,
  });
  const mfaRecovery = useQuery({
    queryKey: ["management", "mfa-recovery"],
    queryFn: async () =>
      (await api.get<MfaRecoveryRequest[]>("/management/mfa-recovery-requests"))
        .data,
    enabled: isSuperAdmin,
  });
  return { overview, members, groups, catalog, organizations, mfaRecovery };
}

export function AdminPlaceholderPage() {
  const { user } = useAuth();
  const [searchParams] = useSearchParams();
  if (user?.role === "DIRECTOR" && searchParams.get("view") !== "management") {
    return <DirectorDashboardPage />;
  }
  return <AdministrationPage />;
}

function AdministrationPage() {
  const { t } = useTranslation(["admin", "common"]);
  const { user } = useAuth();
  const isSuperAdmin = user?.role === "SUPER_ADMIN";
  const [searchParams, setSearchParams] = useSearchParams();
  const [memberOffset, setMemberOffset] = useState(0);
  const [memberSearch, setMemberSearch] = useState("");
  const [groupOffset, setGroupOffset] = useState(0);
  const [organizationOffset, setOrganizationOffset] = useState(0);
  const data = useManagementData(
    isSuperAdmin,
    memberOffset,
    memberSearch,
    groupOffset,
    organizationOffset,
  );
  const tabs: { id: Tab; label: string }[] = [
    { id: "overview", label: t("overview") },
    { id: "members", label: t("members") },
    { id: "user-operations", label: t("accessManagement") },
    { id: "groups", label: t("groupsTab") },
    { id: "assignments", label: t("assignmentsTab") },
    { id: "catalog", label: t("structure") },
    ...(isSuperAdmin
      ? [
          { id: "organizations" as Tab, label: t("organizationsTab") },
          { id: "mfa-recovery" as Tab, label: t("mfaRecoveryTab") },
        ]
      : []),
  ];
  const requestedTab = searchParams.get("tab");
  const tab = tabs.some((item) => item.id === requestedTab)
    ? (requestedTab as Tab)
    : "overview";
  const setTab = (nextTab: Tab) => {
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set("tab", nextTab);
    setSearchParams(nextParams, { replace: true });
  };
  const activeRequests: RequestState[] =
    tab === "overview"
      ? [data.overview]
      : tab === "members"
        ? [data.members, data.catalog]
        : tab === "user-operations"
          ? [data.members]
          : tab === "groups"
            ? [data.groups, data.members, data.catalog]
            : tab === "assignments"
              ? [data.groups]
              : tab === "catalog"
                ? [data.catalog]
                : tab === "mfa-recovery"
                  ? [data.mfaRecovery]
                  : [data.organizations];
  const activeError = activeRequests.find((request) => request.isError);
  const isActiveLoading = activeRequests.some((request) => request.isLoading);
  const retryActiveTab = () =>
    activeRequests.forEach((request) => void request.refetch());
  return (
    <div>
      <header className="mb-6 border-b border-[var(--color-border)] border-l-4 border-l-[var(--color-brand-600)] bg-white px-5 py-5 sm:px-6">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--color-brand-600)]">
          {t("managementKicker")}
        </p>
        <div className="mt-1 flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="font-display text-2xl font-bold tracking-[-0.025em] text-[var(--color-ink)]">
              {data.overview.data?.organization.name ??
                t("organizationFallback")}
            </h1>
            <p className="mt-1 text-sm text-[var(--color-muted)]">
              {isSuperAdmin
                ? t("globalAdministration")
                : t("organizationStructure")}
            </p>
          </div>
          <span className="rounded-[5px] border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1.5 text-xs font-semibold text-[var(--color-ink-soft)]">
            {isSuperAdmin
              ? t("common:roles.SUPER_ADMIN")
              : t("common:roles.DIRECTOR")}
          </span>
        </div>
      </header>
      <nav className="mb-6 flex gap-1 overflow-x-auto border-b border-[var(--color-border)]">
        {tabs.map((item) => (
          <button
            key={item.id}
            onClick={() => setTab(item.id)}
            className={`-mb-px border-b-2 px-4 py-2.5 text-sm font-medium ${tab === item.id ? "border-[var(--color-brand-500)] text-[var(--color-brand-700)]" : "border-transparent text-[var(--color-muted)] hover:text-[var(--color-ink-soft)]"}`}
          >
            {item.label}
          </button>
        ))}
      </nav>
      {data.overview.isError && tab !== "overview" && (
        <div className="mb-5">
          <ErrorState
            compact
            error={data.overview.error}
            message={t("organizationNameLoadError")}
            onRetry={() => void data.overview.refetch()}
          />
        </div>
      )}
      {isActiveLoading && <LoadingState label={t("loadingManagement")} />}
      {activeError && (
        <ErrorState error={activeError.error} onRetry={retryActiveTab} />
      )}
      {!isActiveLoading && !activeError && (
        <>
          {tab === "overview" && <Overview overview={data.overview.data} />}
          {tab === "members" && (
            <Members
              members={data.members.data?.items ?? []}
              pagination={data.members.data}
              isFetching={data.members.isFetching}
              onPageChange={setMemberOffset}
              search={memberSearch}
              onSearchChange={(value) => {
                setMemberSearch(value);
                setMemberOffset(0);
              }}
              catalog={data.catalog.data}
              canCreateElevatedRoles={isSuperAdmin}
            />
          )}
          {tab === "user-operations" && (
            <UserOperations
              members={data.members.data?.items ?? []}
              canCreateElevatedRoles={isSuperAdmin}
            />
          )}
          {tab === "groups" && (
            <Groups
              groups={data.groups.data?.items ?? []}
              pagination={data.groups.data}
              isFetching={data.groups.isFetching}
              onPageChange={setGroupOffset}
              members={data.members.data?.items ?? []}
              catalog={data.catalog.data}
            />
          )}
          {tab === "assignments" && (
            <GroupAssignments groups={data.groups.data?.items ?? []} />
          )}
          {tab === "catalog" && <Catalog catalog={data.catalog.data} />}
          {tab === "organizations" && isSuperAdmin && (
            <Organizations
              organizations={data.organizations.data?.items ?? []}
              pagination={data.organizations.data}
              isFetching={data.organizations.isFetching}
              onPageChange={setOrganizationOffset}
            />
          )}
          {tab === "mfa-recovery" && isSuperAdmin && (
            <MfaRecoveryRequests requests={data.mfaRecovery.data ?? []} />
          )}
        </>
      )}
    </div>
  );
}

function Overview({ overview }: { overview: ManagementOverview | undefined }) {
  const { t } = useTranslation("admin");
  const { formatNumber } = useLocaleFormatters();
  if (!overview) return <ErrorState message={t("overviewUnavailable")} />;
  const metrics: [string, number, string][] = [
    [t("membersMetric"), overview.members_count, t("membersMetricNote")],
    [t("studentsMetric"), overview.students_count, t("studentsMetricNote")],
    [t("teachersMetric"), overview.teachers_count, t("teachersMetricNote")],
    [t("groupsMetric"), overview.groups_count, t("groupsMetricNote")],
    [t("reportsMetric"), overview.active_reports_count, t("reportsMetricNote")],
  ];
  return (
    <div>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        {metrics.map(([label, value, note]) => (
          <div key={label} className="card p-5">
            <p className="text-sm font-semibold text-[var(--color-muted)]">
              {label}
            </p>
            <p className="mt-2 font-display text-3xl font-extrabold text-[var(--color-ink)]">
              {formatNumber(value)}
            </p>
            <p className="mt-2 text-xs text-[var(--color-muted)]">{note}</p>
          </div>
        ))}
      </div>
      <section className="card mt-6 p-6">
        <h2 className="font-display text-lg font-bold text-[var(--color-ink)]">
          {t("workingStructure")}
        </h2>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-[var(--color-ink-soft)]">
          {t("workingStructureDescription")}
        </p>
      </section>
    </div>
  );
}

function Members({
  members,
  pagination,
  isFetching,
  onPageChange,
  search,
  onSearchChange,
  catalog,
  canCreateElevatedRoles,
}: {
  members: ManagementMember[];
  pagination: PaginationInfo | undefined;
  isFetching: boolean;
  onPageChange: (offset: number) => void;
  search: string;
  onSearchChange: (value: string) => void;
  catalog: ManagementCatalog | undefined;
  canCreateElevatedRoles: boolean;
}) {
  const { t } = useTranslation(["admin", "common"]);
  const roleLabels: Record<Role, string> = {
    STUDENT: t(`common:${ROLE_TRANSLATION_KEYS.STUDENT}`),
    TEACHER: t(`common:${ROLE_TRANSLATION_KEYS.TEACHER}`),
    DIRECTOR: t(`common:${ROLE_TRANSLATION_KEYS.DIRECTOR}`),
    SUPER_ADMIN: t(`common:${ROLE_TRANSLATION_KEYS.SUPER_ADMIN}`),
  };
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>("STUDENT");
  const [departmentId, setDepartmentId] = useState("");
  const [specialtyId, setSpecialtyId] = useState("");
  const create = useMutation({
    mutationFn: async () =>
      api.post("/management/members", {
        full_name: fullName,
        email,
        password: password || undefined,
        role,
        department_id: departmentId || null,
        specialty_id: specialtyId || null,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["management", "members"],
      });
      setOpen(false);
      setFullName("");
      setEmail("");
      setPassword("");
      setDepartmentId("");
      setSpecialtyId("");
    },
  });
  const permittedRoles: Role[] = canCreateElevatedRoles
    ? ["STUDENT", "TEACHER", "DIRECTOR", "SUPER_ADMIN"]
    : ["STUDENT", "TEACHER"];
  return (
    <div>
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-display text-xl font-bold text-[var(--color-ink)]">
            {t("members")}
          </h2>
          <p className="mt-1 text-sm text-[var(--color-muted)]">
            {t("membersDescription")}
          </p>
        </div>
        <button
          onClick={() => setOpen((value) => !value)}
          className="btn btn-primary"
        >
          <PlusIcon className="size-4" />
          {t("member")}
        </button>
      </div>
      <label className="mb-4 block max-w-md">
        <span className="sr-only">{t("searchMembersLabel")}</span>
        <input
          value={search}
          onChange={(event) => onSearchChange(event.target.value)}
          className="input"
          placeholder={t("searchMembersPlaceholder")}
          aria-label={t("searchMembersLabel")}
        />
      </label>
      {open && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate();
          }}
          className="mb-5 grid gap-3 rounded-2xl border border-[var(--color-brand-100)] bg-[var(--color-brand-50)] p-5 md:grid-cols-2"
        >
          <Input
            label={t("fullName")}
            value={fullName}
            onChange={setFullName}
            required
          />
          <Input
            label={t("common:email")}
            value={email}
            onChange={setEmail}
            type="email"
            required
          />
          <Input
            label={t("passwordForNewUser")}
            value={password}
            onChange={setPassword}
            type="password"
            placeholder={t("passwordExistingEmailHint")}
          />
          <label className="block">
            <span className="form-label">{t("role")}</span>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value as Role)}
              className="input"
            >
              {permittedRoles.map((value) => (
                <option key={value} value={value}>
                  {roleLabels[value]}
                </option>
              ))}
            </select>
          </label>
          {role === "TEACHER" && (
            <Select
              label={t("department")}
              value={departmentId}
              onChange={setDepartmentId}
              options={catalog?.departments ?? []}
            />
          )}
          {role === "STUDENT" && (
            <Select
              label={t("specialty")}
              value={specialtyId}
              onChange={setSpecialtyId}
              options={catalog?.specialties ?? []}
            />
          )}
          {create.isError && (
            <p className="text-sm text-[var(--color-danger-500)]">
              {t("createMemberError")}
            </p>
          )}
          <div className="flex items-end justify-end gap-2 md:col-span-2">
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="btn btn-ghost"
            >
              {t("common:cancel")}
            </button>
            <button disabled={create.isPending} className="btn btn-primary">
              {t("createMembership")}
            </button>
          </div>
        </form>
      )}
      <div className="table-frame">
        <table className="table-base">
          <thead>
            <tr>
              <th className="px-5 py-3">{t("member")}</th>
              <th className="px-5 py-3">{t("role")}</th>
              <th className="px-5 py-3">{t("groupsTab")}</th>
            </tr>
          </thead>
          <tbody>
            {members.map((member) => (
              <tr key={member.id}>
                <td className="px-5 py-3">
                  <p className="font-medium text-[var(--color-ink)]">
                    {member.full_name}
                  </p>
                  <p className="text-xs text-[var(--color-muted)]">
                    {member.email}
                  </p>
                </td>
                <td className="px-5 py-3">
                  <span className="rounded-full bg-[var(--color-brand-50)] px-2 py-1 text-xs font-medium text-[var(--color-brand-700)]">
                    {roleLabels[member.role]}
                  </span>
                </td>
                <td className="px-5 py-3 text-[var(--color-muted)]">
                  {member.group_names.join(", ") || "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {members.length === 0 && (
          <p className="p-6 text-center text-sm text-[var(--color-muted)]">
            {search ? t("noSearchMembers") : t("noOrganizationMembers")}
          </p>
        )}
      </div>
      {pagination && (
        <PaginationControls
          pagination={pagination}
          onPageChange={onPageChange}
          isFetching={isFetching}
          label={t("members")}
        />
      )}
    </div>
  );
}

function Groups({
  groups,
  pagination,
  isFetching,
  onPageChange,
  members,
  catalog,
}: {
  groups: ManagementGroup[];
  pagination: PaginationInfo | undefined;
  isFetching: boolean;
  onPageChange: (offset: number) => void;
  members: ManagementMember[];
  catalog: ManagementCatalog | undefined;
}) {
  const { t } = useTranslation(["admin", "groups", "common"]);
  const { formatCount, formatNumber } = useLocaleFormatters();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [year, setYear] = useState("");
  const [specialtyId, setSpecialtyId] = useState("");
  const [teacherId, setTeacherId] = useState("");
  const [assignments, setAssignments] = useState<Record<string, string>>({});
  const teachers = useMemo(
    () =>
      members.filter(
        (member) => member.role === "TEACHER" && member.profile_id,
      ),
    [members],
  );
  const create = useMutation({
    mutationFn: async () =>
      api.post("/management/groups", {
        name,
        academic_year: year || null,
        specialty_id: specialtyId || null,
        teacher_ids: teacherId ? [teacherId] : [],
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["management", "groups"],
      });
      setOpen(false);
      setName("");
      setYear("");
      setSpecialtyId("");
      setTeacherId("");
    },
  });
  const assign = useMutation({
    mutationFn: async ({
      groupId,
      selectedTeacherId,
    }: {
      groupId: string;
      selectedTeacherId: string;
    }) =>
      api.post(`/management/groups/${groupId}/teachers`, {
        teacher_ids: [selectedTeacherId],
      }),
    onSuccess: () =>
      void queryClient.invalidateQueries({
        queryKey: ["management", "groups"],
      }),
  });
  return (
    <div>
      <div className="mb-5 flex items-center justify-between">
        <div>
          <h2 className="font-display text-xl font-bold text-[var(--color-ink)]">
            {t("groupsTab")}
          </h2>
          <p className="mt-1 text-sm text-[var(--color-muted)]">
            {t("groupsDescription")}
          </p>
        </div>
        <button
          onClick={() => setOpen((value) => !value)}
          className="btn btn-primary"
        >
          <PlusIcon className="size-4" />
          {t("groups:group")}
        </button>
      </div>
      {open && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate();
          }}
          className="mb-5 grid gap-3 rounded-2xl border border-[var(--color-brand-100)] bg-[var(--color-brand-50)] p-5 md:grid-cols-2"
        >
          <Input
            label={t("groupName")}
            value={name}
            onChange={setName}
            placeholder={t("groupNameExample")}
            required
          />
          <Input
            label={t("academicYear")}
            value={year}
            onChange={setYear}
            placeholder="2025–2026"
          />
          <Select
            label={t("specialty")}
            value={specialtyId}
            onChange={setSpecialtyId}
            options={catalog?.specialties ?? []}
          />
          <label className="block">
            <span className="form-label">{t("primaryTeacher")}</span>
            <select
              value={teacherId}
              onChange={(e) => setTeacherId(e.target.value)}
              className="input"
            >
              <option value="">{t("assignLater")}</option>
              {teachers.map((teacher) => (
                <option key={teacher.profile_id} value={teacher.profile_id!}>
                  {teacher.full_name}
                </option>
              ))}
            </select>
          </label>
          <div className="flex justify-end gap-2 md:col-span-2">
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="btn btn-ghost"
            >
              {t("common:cancel")}
            </button>
            <button disabled={create.isPending} className="btn btn-primary">
              {t("createGroup")}
            </button>
          </div>
        </form>
      )}
      <div className="grid gap-4 md:grid-cols-2">
        {groups.map((group) => (
          <article key={group.id} className="card p-5">
            <div className="flex items-start justify-between">
              <div>
                <p className="font-mono-code text-lg font-semibold text-[var(--color-ink)]">
                  {group.name}
                </p>
                <p className="mt-1 text-sm text-[var(--color-muted)]">
                  {group.academic_year ?? t("academicYearMissing")} ·{" "}
                  {formatCount(group.student_count, (values) =>
                    t("groups:studentCount", values),
                  )}
                </p>
              </div>
              <span className="rounded-full bg-[var(--color-surface)] px-2 py-1 text-xs text-[var(--color-muted)]">
                {formatNumber(group.teacher_names.length)} {t("teacherShort")}
              </span>
            </div>
            <p className="mt-4 text-sm text-[var(--color-ink-soft)]">
              {group.teacher_names.join(", ") || t("teacherNotAssigned")}
            </p>
            {teachers.some(
              (teacher) => !group.teacher_ids.includes(teacher.profile_id!),
            ) && (
              <div className="mt-4 flex gap-2">
                <select
                  value={assignments[group.id] ?? ""}
                  onChange={(e) =>
                    setAssignments({
                      ...assignments,
                      [group.id]: e.target.value,
                    })
                  }
                  className="input py-1.5"
                >
                  <option value="">{t("addTeacher")}</option>
                  {teachers
                    .filter(
                      (teacher) =>
                        !group.teacher_ids.includes(teacher.profile_id!),
                    )
                    .map((teacher) => (
                      <option
                        key={teacher.profile_id}
                        value={teacher.profile_id!}
                      >
                        {teacher.full_name}
                      </option>
                    ))}
                </select>
                <button
                  disabled={!assignments[group.id] || assign.isPending}
                  onClick={() =>
                    assign.mutate({
                      groupId: group.id,
                      selectedTeacherId: assignments[group.id],
                    })
                  }
                  className="btn btn-secondary px-3 py-2 text-xs text-[var(--color-brand-600)]"
                >
                  {t("assign")}
                </button>
              </div>
            )}
          </article>
        ))}
      </div>
      {groups.length === 0 && (
        <div className="empty-state text-sm text-[var(--color-muted)]">
          {t("groupsEmpty")}
        </div>
      )}
      {pagination && (
        <PaginationControls
          pagination={pagination}
          onPageChange={onPageChange}
          isFetching={isFetching}
          label={t("groupsTab")}
        />
      )}
    </div>
  );
}

function Catalog({ catalog }: { catalog: ManagementCatalog | undefined }) {
  const { t } = useTranslation(["admin", "common"]);
  const queryClient = useQueryClient();
  const [departmentName, setDepartmentName] = useState("");
  const [specialtyName, setSpecialtyName] = useState("");
  const [code, setCode] = useState("");
  const [departmentId, setDepartmentId] = useState("");
  const refresh = () =>
    void queryClient.invalidateQueries({ queryKey: ["management", "catalog"] });
  const addDepartment = useMutation({
    mutationFn: async () =>
      api.post("/management/departments", { name: departmentName }),
    onSuccess: () => {
      setDepartmentName("");
      refresh();
    },
  });
  const addSpecialty = useMutation({
    mutationFn: async () =>
      api.post("/management/specialties", {
        name: specialtyName,
        code: code || null,
        department_id: departmentId,
      }),
    onSuccess: () => {
      setSpecialtyName("");
      setCode("");
      refresh();
    },
  });
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] p-5">
        <h2 className="font-display text-xl font-bold text-[var(--color-ink)]">
          {t("departments")}
        </h2>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            addDepartment.mutate();
          }}
          className="mt-4 flex gap-2"
        >
          <input
            value={departmentName}
            onChange={(e) => setDepartmentName(e.target.value)}
            className="input"
            placeholder={t("departmentName")}
            required
          />
          <button
            disabled={addDepartment.isPending}
            className="rounded-lg bg-[var(--color-brand-500)] px-4 text-sm font-semibold text-white"
          >
            {t("common:add")}
          </button>
        </form>
        <div className="mt-5 space-y-2">
          {catalog?.departments.map((department) => (
            <div
              key={department.id}
              className="rounded-lg bg-[var(--color-surface)] px-3 py-2 text-sm text-[var(--color-ink-soft)]"
            >
              {department.name}
            </div>
          ))}
        </div>
      </section>
      <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] p-5">
        <h2 className="font-display text-xl font-bold text-[var(--color-ink)]">
          {t("specialties")}
        </h2>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            addSpecialty.mutate();
          }}
          className="mt-4 grid gap-2"
        >
          <Select
            label={t("department")}
            value={departmentId}
            onChange={setDepartmentId}
            options={catalog?.departments ?? []}
            required
          />
          <Input
            label={t("specialtyName")}
            value={specialtyName}
            onChange={setSpecialtyName}
            required
          />
          <Input label={t("codeOptional")} value={code} onChange={setCode} />
          <button
            disabled={addSpecialty.isPending || !departmentId}
            className="mt-1 rounded-lg bg-[var(--color-brand-500)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-60"
          >
            {t("addSpecialty")}
          </button>
        </form>
        <div className="mt-5 space-y-2">
          {catalog?.specialties.map((specialty) => (
            <div
              key={specialty.id}
              className="flex justify-between rounded-lg bg-[var(--color-surface)] px-3 py-2 text-sm text-[var(--color-ink-soft)]"
            >
              <span>{specialty.name}</span>
              {specialty.code && (
                <span className="font-mono-code text-xs text-[var(--color-muted)]">
                  {specialty.code}
                </span>
              )}
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function Organizations({
  organizations,
  pagination,
  isFetching,
  onPageChange,
}: {
  organizations: OrganizationOut[];
  pagination: PaginationInfo | undefined;
  isFetching: boolean;
  onPageChange: (offset: number) => void;
}) {
  const { t } = useTranslation(["admin", "common"]);
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const create = useMutation({
    mutationFn: async () =>
      api.post("/management/organizations", { name, slug }),
    onSuccess: () => {
      setName("");
      setSlug("");
      void queryClient.invalidateQueries({
        queryKey: ["management", "organizations"],
      });
    },
  });
  return (
    <div className="grid gap-5 lg:grid-cols-[0.8fr_1.2fr]">
      <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] p-5">
        <h2 className="font-display text-xl font-bold text-[var(--color-ink)]">
          {t("newOrganization")}
        </h2>
        <p className="mt-1 text-sm text-[var(--color-muted)]">
          {t("superAdminMembershipHint")}
        </p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate();
          }}
          className="mt-5 space-y-3"
        >
          <Input
            label={t("common:name")}
            value={name}
            onChange={setName}
            required
          />
          <Input
            label={t("signInSlug")}
            value={slug}
            onChange={(value) =>
              setSlug(value.toLowerCase().replace(/[^a-z0-9-]/g, ""))
            }
            placeholder="college-almaty"
            required
          />
          {create.isError && (
            <p className="text-sm text-[var(--color-danger-500)]">
              {t("organizationCreateError")}
            </p>
          )}
          <button
            disabled={create.isPending}
            className="w-full rounded-lg bg-[var(--color-brand-500)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-60"
          >
            {t("createOrganization")}
          </button>
        </form>
      </section>
      <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] p-5">
        <h2 className="font-display text-xl font-bold text-[var(--color-ink)]">
          {t("allOrganizations")}
        </h2>
        <div className="mt-4 space-y-2">
          {organizations.map((organization) => (
            <div
              key={organization.id}
              className="flex items-center justify-between rounded-lg bg-[var(--color-surface)] px-4 py-3"
            >
              <span className="font-medium text-[var(--color-ink)]">
                {organization.name}
              </span>
              <span className="font-mono-code text-xs text-[var(--color-muted)]">
                {organization.slug}
              </span>
            </div>
          ))}
        </div>
        {pagination && (
          <PaginationControls
            pagination={pagination}
            onPageChange={onPageChange}
            isFetching={isFetching}
            label={t("organizationsTab")}
          />
        )}
      </section>
    </div>
  );
}

function MfaRecoveryRequests({ requests }: { requests: MfaRecoveryRequest[] }) {
  const { t } = useTranslation("admin");
  const { formatDateTime } = useLocaleFormatters();
  const queryClient = useQueryClient();
  const approve = useMutation({
    mutationFn: async (id: string) =>
      api.post(`/management/mfa-recovery-requests/${id}/approve`),
    onSuccess: () =>
      void queryClient.invalidateQueries({
        queryKey: ["management", "mfa-recovery"],
      }),
  });
  return (
    <section className="card p-6">
      <h2 className="font-display text-xl font-bold text-[var(--color-ink)]">
        {t("recoveryRequests")}
      </h2>
      <p className="mt-2 max-w-2xl text-sm text-[var(--color-ink-soft)]">
        {t("recoveryRequestsDescription")}
      </p>
      <div className="mt-5 space-y-3">
        {requests.map((request) => (
          <article
            key={request.id}
            className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[var(--color-border)] p-4"
          >
            <div>
              <p className="font-semibold text-[var(--color-ink)]">
                {request.user_name}
              </p>
              <p className="text-sm text-[var(--color-muted)]">
                {request.user_email} ·{" "}
                {t("expiresAt", {
                  date: formatDateTime(request.expires_at),
                })}
              </p>
            </div>
            <button
              disabled={approve.isPending}
              onClick={() => approve.mutate(request.id)}
              className="btn btn-primary"
            >
              {t("approveReenrollment")}
            </button>
          </article>
        ))}
        {requests.length === 0 && (
          <p className="rounded-xl bg-[var(--color-surface)] p-4 text-sm text-[var(--color-muted)]">
            {t("noRecoveryRequests")}
          </p>
        )}
      </div>
      {approve.isError && (
        <p className="mt-4 text-sm text-[var(--color-danger-500)]" role="alert">
          {t("recoveryApprovalError")}
        </p>
      )}
    </section>
  );
}

function Input({
  label,
  value,
  onChange,
  type = "text",
  placeholder,
  required = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  placeholder?: string;
  required?: boolean;
}) {
  return (
    <label className="block">
      <span className="form-label">{label}</span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="input"
        required={required}
      />
    </label>
  );
}
function Select({
  label,
  value,
  onChange,
  options,
  required = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { id: string; name: string }[];
  required?: boolean;
}) {
  const { t } = useTranslation("admin");
  return (
    <label className="block">
      <span className="form-label">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="input"
        required={required}
      >
        <option value="">{t("notSelected")}</option>
        {options.map((option) => (
          <option key={option.id} value={option.id}>
            {option.name}
          </option>
        ))}
      </select>
    </label>
  );
}
