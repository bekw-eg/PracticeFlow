import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./app/AppShell";
import { ProtectedRoute } from "./app/ProtectedRoute";
import { useAuth } from "./features/auth/useAuth";
import { LoginPage } from "./features/auth/LoginPage";
import { CompleteAccessPage } from "./features/auth/CompleteAccessPage";
import { MfaPage } from "./features/auth/MfaPage";
import { MyGroupsPage } from "./features/groups/MyGroupsPage";
import { GroupDetailPage } from "./features/groups/GroupDetailPage";
import { TemplatesPage } from "./features/templates/TemplatesPage";
import { StudentReportsPage } from "./features/reports/StudentReportsPage";
import { AdminPlaceholderPage } from "./features/admin/AdminPlaceholderPage";
import { AuditLogPage } from "./features/audit/AuditLogPage";
import { StudentProfilePage } from "./features/profile/StudentProfilePage";
import { TeacherReportPage } from "./features/reports/TeacherReportPage";
import { CheckProfilesPage } from "./features/documentChecks/CheckProfilesPage";
import { CheckProfileRuleEditorPage } from "./features/documentChecks/CheckProfileRuleEditorPage";
import { TeacherDocumentChecksPage } from "./features/documentChecks/TeacherDocumentChecksPage";
import { ReviewGroupsPage, ReviewGroupPage } from "./features/documentChecks/ReviewGroupsPage";
import { TeacherDocumentReviewPage } from "./features/documentChecks/TeacherDocumentReviewPage";
import { ToastViewport } from "./components/ToastViewport";
import { LoadingState } from "./components/ui/StateViews";
import { DisciplinePage, DisciplinesPage, TopicPage } from "./features/disciplines/DisciplinePages";
import { useTranslation } from "react-i18next";

// The document editor pulls in Tiptap/ProseMirror, by far the heaviest
// dependency in the app. Lazy-loading it means someone who only ever visits
// My Groups or Reports never downloads it at all.
const TemplateEditorPage = lazy(() => import("./features/documents/TemplateEditorPage").then((m) => ({ default: m.TemplateEditorPage })));
const ReportEditorPage = lazy(() => import("./features/documents/ReportEditorPage").then((m) => ({ default: m.ReportEditorPage })));

function EditorFallback() {
  const { t } = useTranslation("editor");
  return <LoadingState label={t("loadingEditor")} />;
}

function RoleLandingRedirect() {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  if (user.role === "TEACHER") {
    const documentCheckEnabled = user.features?.document_check_enabled ?? true;
    return <Navigate to={documentCheckEnabled ? "/document-checks" : "/groups"} replace />;
  }
  if (user.role === "STUDENT") return <Navigate to="/reports" replace />;
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
          path="/templates"
          element={
            <ProtectedRoute allowedRoles={["TEACHER"]}>
              <TemplatesPage />
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
        <Route
          path="/templates/:templateId/versions/:versionId"
          element={
            <ProtectedRoute allowedRoles={["TEACHER"]}>
              <Suspense fallback={<EditorFallback />}>
                <TemplateEditorPage />
              </Suspense>
            </ProtectedRoute>
          }
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
          path="/reports"
          element={
            <ProtectedRoute allowedRoles={["STUDENT"]}>
              <StudentReportsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/reports/:reportId/edit"
          element={
            <ProtectedRoute allowedRoles={["STUDENT"]}>
              <Suspense fallback={<EditorFallback />}>
                <ReportEditorPage />
              </Suspense>
            </ProtectedRoute>
          }
        />
        <Route
          path="/profile"
          element={
            <ProtectedRoute allowedRoles={["STUDENT"]}>
              <StudentProfilePage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/groups/:groupId/reports/:reportId"
          element={
            <ProtectedRoute allowedRoles={["TEACHER"]}>
              <TeacherReportPage />
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
      </Route>
    </Routes>
    <ToastViewport />
    </>
  );
}
