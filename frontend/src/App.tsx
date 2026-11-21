import { Navigate, Route, Routes } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowRightStartOnRectangleIcon } from "@heroicons/react/24/outline";
import { AppShell } from "./app/AppShell";
import { ProtectedRoute } from "./app/ProtectedRoute";
import { useAuth } from "./features/auth/useAuth";
import { LoginPage } from "./features/auth/LoginPage";
import { CompleteAccessPage } from "./features/auth/CompleteAccessPage";
import { MfaPage } from "./features/auth/MfaPage";
import { MyGroupsPage } from "./features/groups/MyGroupsPage";
import { GroupDetailPage } from "./features/groups/GroupDetailPage";
import { AdminPlaceholderPage } from "./features/admin/AdminPlaceholderPage";
import { AuditLogPage } from "./features/audit/AuditLogPage";
import { CheckProfilesPage } from "./features/documentChecks/CheckProfilesPage";
import { CheckProfileRuleEditorPage } from "./features/documentChecks/CheckProfileRuleEditorPage";
import { TeacherDocumentChecksPage } from "./features/documentChecks/TeacherDocumentChecksPage";
import { ReviewGroupsPage, ReviewGroupPage } from "./features/documentChecks/ReviewGroupsPage";
import { TeacherDocumentReviewPage } from "./features/documentChecks/TeacherDocumentReviewPage";
import { ToastViewport } from "./components/ToastViewport";
import { DisciplinePage, DisciplinesPage, TopicPage } from "./features/disciplines/DisciplinePages";

function StudentWorkspaceUnavailablePage() {
  const { logout } = useAuth();
  const { t } = useTranslation(["common", "auth"]);
  return (
    <section className="mx-auto mt-12 max-w-lg rounded-2xl border border-[var(--color-border)] bg-white p-8 text-center shadow-[var(--shadow-card)]">
      <h1 className="font-display text-xl font-bold text-[var(--color-ink)]">
        {t("common:studentWorkspaceUnavailableTitle")}
      </h1>
      <p className="mt-3 text-sm leading-6 text-[var(--color-muted)]">
        {t("common:studentWorkspaceUnavailableDescription")}
      </p>
      <button
        type="button"
        onClick={() => void logout()}
        className="btn btn-primary mt-6 inline-flex items-center gap-2"
      >
        <ArrowRightStartOnRectangleIcon className="size-4" aria-hidden="true" />
        {t("auth:signOut")}
      </button>
    </section>
  );
}

function RoleLandingRedirect() {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  if (user.role === "TEACHER") {
    const documentCheckEnabled = user.features?.document_check_enabled ?? true;
    return <Navigate to={documentCheckEnabled ? "/document-checks" : "/groups"} replace />;
  }
  if (user.role === "STUDENT") return <Navigate to="/student-unavailable" replace />;
  return <Navigate to="/admin" replace />;
}

export function App() {
  return (
    <>
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/access" element={<CompleteAccessPage />} />
      <Route path="/mfa" element={<MfaPage />} />
      <Route
        element={
          <ProtectedRoute>
            <AppShell />
          </ProtectedRoute>
        }
      >
        <Route path="/" element={<RoleLandingRedirect />} />
        <Route path="/disciplines" element={<ProtectedRoute allowedRoles={["TEACHER"]}><DisciplinesPage /></ProtectedRoute>} />
        <Route path="/disciplines/:disciplineId" element={<ProtectedRoute allowedRoles={["TEACHER"]}><DisciplinePage /></ProtectedRoute>} />
        <Route path="/disciplines/:disciplineId/topics/:topicId" element={<ProtectedRoute allowedRoles={["TEACHER"]}><TopicPage /></ProtectedRoute>} />
        <Route
          path="/groups"
          element={
            <ProtectedRoute allowedRoles={["TEACHER"]}>
              <MyGroupsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/groups/:groupId"
          element={
            <ProtectedRoute allowedRoles={["TEACHER"]}>
              <GroupDetailPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/check-profiles"
          element={<ProtectedRoute allowedRoles={["TEACHER"]}><CheckProfilesPage /></ProtectedRoute>}
        />
        <Route
          path="/check-profiles/:profileId/versions/:versionId"
          element={<ProtectedRoute allowedRoles={["TEACHER"]}><CheckProfileRuleEditorPage /></ProtectedRoute>}
        />
        <Route path="/review-groups" element={<ProtectedRoute allowedRoles={["TEACHER"]}><ReviewGroupsPage /></ProtectedRoute>} />
        <Route path="/review-groups/:groupId" element={<ProtectedRoute allowedRoles={["TEACHER"]}><ReviewGroupPage /></ProtectedRoute>} />
        <Route
          path="/document-checks"
          element={<ProtectedRoute allowedRoles={["TEACHER"]}><TeacherDocumentChecksPage /></ProtectedRoute>}
        />
        <Route
          path="/document-checks/:submissionId"
          element={<ProtectedRoute allowedRoles={["TEACHER"]}><TeacherDocumentReviewPage /></ProtectedRoute>}
        />
        <Route
          path="/student-unavailable"
          element={
            <ProtectedRoute allowedRoles={["STUDENT"]}>
              <StudentWorkspaceUnavailablePage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin"
          element={
            <ProtectedRoute allowedRoles={["SUPER_ADMIN", "DIRECTOR"]}>
              <AdminPlaceholderPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/audit"
          element={
            <ProtectedRoute allowedRoles={["SUPER_ADMIN"]}>
              <AuditLogPage />
            </ProtectedRoute>
          }
        />
        <Route path="*" element={<RoleLandingRedirect />} />
      </Route>
    </Routes>
    <ToastViewport />
    </>
  );
}
