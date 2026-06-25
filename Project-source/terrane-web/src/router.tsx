/** Frontend routing — URL path-based i18n. License guard (LockedPage when locked);
 *  public auth pages (login/register/forgot/reset/verify); protected workbench home (RequireAuth). */

import { useEffect, type ReactNode } from "react";
import { Navigate, Outlet, createBrowserRouter, useParams } from "react-router";

import { useAuth } from "@/auth/AuthContext";
import { RequireAuth } from "@/auth/RequireAuth";
import { RequireLicense } from "@/auth/RequireLicense";
import { applyLang } from "@/i18n";
import { detectLang, isSupported } from "@/i18n/langs";
import { WorkbenchLayout } from "@/components/WorkbenchLayout";
import { KbLayout } from "@/components/KbLayout";
import { ChatPage } from "@/pages/ChatPage";
import { GraphPage } from "@/pages/GraphPage";
import { HomePage } from "@/pages/HomePage";
import { MemoryPage } from "@/pages/MemoryPage";
import { OverviewPage } from "@/pages/OverviewPage";
import { SourcePreviewPage } from "@/pages/SourcePreviewPage";
import { OverviewPage as KbOverviewPage } from "@/pages/kb/OverviewPage";
import { SourcesPage } from "@/pages/kb/SourcesPage";
import { StudioPage } from "@/pages/kb/StudioPage";
import { WikiPage } from "@/pages/kb/WikiPage";
import { QaPage } from "@/pages/kb/QaPage";
import { RecallPage } from "@/pages/kb/RecallPage";
import { McpPage } from "@/pages/kb/McpPage";
import { SettingsPage as KbSettingsPage } from "@/pages/kb/SettingsPage";
import { ModelSettingsPage } from "@/pages/settings/ModelSettingsPage";
import { LanguageSettingsPage } from "@/pages/settings/LanguageSettingsPage";
import { SecuritySettingsPage } from "@/pages/settings/SecuritySettingsPage";
import { ForgotPasswordPage } from "@/pages/auth/ForgotPasswordPage";
import { LoginPage } from "@/pages/auth/LoginPage";
import { RegisterPage } from "@/pages/auth/RegisterPage";
import { ResetPasswordPage } from "@/pages/auth/ResetPasswordPage";
import { VerifyEmailPage } from "@/pages/auth/VerifyEmailPage";

function LangLayout() {
  const { lang } = useParams();
  const valid = !!lang && isSupported(lang);
  useEffect(() => {
    if (lang && isSupported(lang)) applyLang(lang);
  }, [lang]);
  if (!valid) {
    return <Navigate to={`/${detectLang(navigator.languages)}/`} replace />;
  }
  return <Outlet />;
}

/** When already logged in and visiting login/register → redirect to the workbench. */
function GuestOnly({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const { lang } = useParams();
  const seg = lang && isSupported(lang) ? lang : detectLang(navigator.languages);
  if (!loading && user) return <Navigate to={`/${seg}/`} replace />;
  return <>{children}</>;
}

/** Email links without a language prefix (/verify-email, /reset-password) → prepend the browser
 *  language prefix and preserve the query.
 *  Links in emails are kept language-agnostic, with the frontend resolving the language here
 *  (otherwise /verify-email would be treated as :lang and drop the token). */
function LangRedirect({ to }: { to: string }) {
  const seg = detectLang(navigator.languages);
  return <Navigate to={`/${seg}/${to}${window.location.search}`} replace />;
}

export const router = createBrowserRouter([
  { path: "/", element: <Navigate to={`/${detectLang(navigator.languages)}/`} replace /> },
  // Email links (no language prefix): add the prefix and preserve ?token= so they aren't swallowed by /:lang.
  { path: "/verify-email", element: <LangRedirect to="verify-email" /> },
  { path: "/reset-password", element: <LangRedirect to="reset-password" /> },
  {
    path: "/:lang",
    element: <LangLayout />,
    children: [
      // License guard: when locked, everything lands on LockedPage.
      {
        element: <RequireLicense />,
        children: [
          { path: "login", element: <GuestOnly><LoginPage /></GuestOnly> },
          { path: "register", element: <GuestOnly><RegisterPage /></GuestOnly> },
          { path: "forgot-password", element: <ForgotPasswordPage /> },
          { path: "reset-password", element: <ResetPasswordPage /> },
          { path: "verify-email", element: <VerifyEmailPage /> },
          // Protected workbench.
          {
            element: <RequireAuth />,
            children: [
              {
                element: <WorkbenchLayout />,
                children: [
                  { index: true, element: <OverviewPage /> },
                  { path: "kb", element: <HomePage /> },
                  { path: "graph", element: <GraphPage /> },
                  { path: "memory", element: <MemoryPage /> },
                  { path: "chat", element: <ChatPage /> },
                  { path: "settings/models", element: <ModelSettingsPage /> },
                  { path: "settings/security", element: <SecuritySettingsPage /> },
                  { path: "settings/language", element: <LanguageSettingsPage /> },
                  { path: "account", element: <Navigate to="../settings/security" replace /> },
                ],
              },
              // Knowledge base shell (Dify-style IA): entering a KB → the left side switches to the KB's feature nav, with sub-pages as standalone routes.
              {
                path: "kb/:kbId",
                element: <KbLayout />,
                children: [
                  { index: true, element: <Navigate to="overview" replace /> },
                  { path: "overview", element: <KbOverviewPage /> },
                  { path: "sources", element: <SourcesPage /> },
                  { path: "studio", element: <StudioPage /> },
                  { path: "wiki", element: <WikiPage /> },
                  { path: "qa", element: <QaPage /> },
                  { path: "recall", element: <RecallPage /> },
                  { path: "mcp", element: <McpPage /> },
                  { path: "settings", element: <KbSettingsPage /> },
                ],
              },
              // Full-page source preview (without the KB sidebar, with its own back button).
              { path: "kb/:kbId/source/:sourceId", element: <SourcePreviewPage /> },
            ],
          },
        ],
      },
      { path: "*", element: <Navigate to="." replace /> },
    ],
  },
]);
