/** Routing — URL path-based i18n (i18n.md: every page carries a /<lang>/ prefix; the root path
 *  302-redirects based on browser language).
 *  Public: activate (no login required; License unlock is reachable in the locked state, key to
 *  avoiding deadlock).
 *  License-guarded area (RequireLicense polls for revocation/deletion → kicks back to activate):
 *    login (redirects to /admin if already logged in); RequireAuth → /admin management console. */

import { useEffect } from "react";
import { Navigate, Outlet, createBrowserRouter, useParams } from "react-router";

import { useAuth } from "@/auth/AuthContext";
import { RequireAuth } from "@/auth/RequireAuth";
import { RequireLicense } from "@/auth/RequireLicense";
import { RequireSetup } from "@/auth/RequireSetup";
import { applyLang } from "@/i18n";
import { detectLang, isSupported } from "@/i18n/langs";
import { ActivatePage } from "@/pages/activate/ActivatePage";
import { AdminLayout } from "@/pages/admin/AdminLayout";
import { EditPasswordPage } from "@/pages/admin/account/EditPasswordPage";
import { OverviewPage } from "@/pages/admin/OverviewPage";
import { AuditLogsPage } from "@/pages/admin/AuditLogsPage";
import { ChannelsPage } from "@/pages/admin/ChannelsPage";
import { KbOverviewPage } from "@/pages/admin/KbOverviewPage";
import { MembersPage } from "@/pages/admin/MembersPage";
import { BrandingSettingsPage } from "@/pages/admin/settings/BrandingSettingsPage";
import { EmailSettingsPage } from "@/pages/admin/settings/EmailSettingsPage";
import { LicenseSettingsPage } from "@/pages/admin/settings/LicenseSettingsPage";
import { LoginSettingsPage } from "@/pages/admin/settings/LoginSettingsPage";
import { PasswordSettingsPage } from "@/pages/admin/settings/PasswordSettingsPage";
import { SystemUsersPage } from "@/pages/admin/settings/SystemUsersPage";
import { WorkspacesPage } from "@/pages/admin/WorkspacesPage";
import { ChangePasswordPage } from "@/pages/login/ChangePasswordPage";
import { LoginPage } from "@/pages/login/LoginPage";
import { WizardPage } from "@/pages/wizard/WizardPage";

function LangLayout() {
  const { lang } = useParams();
  const valid = !!lang && isSupported(lang);
  // changeLanguage triggers i18next subscriber updates; it must not run during render (React forbids setState during render).
  useEffect(() => {
    if (lang && isSupported(lang)) applyLang(lang);
  }, [lang]);
  if (!valid) {
    return <Navigate to={`/${detectLang(navigator.languages)}/activate`} replace />;
  }
  return <Outlet />;
}

/** Login page guard: a logged-in user visiting /login is redirected straight to /admin. */
function LoginGate() {
  const { user, loading } = useAuth();
  const { lang } = useParams();
  const seg = lang && isSupported(lang) ? lang : detectLang(navigator.languages);
  if (!loading && user) {
    return <Navigate to={`/${seg}/admin`} replace />;
  }
  return <LoginPage />;
}

export const router = createBrowserRouter([
  { path: "/", element: <Navigate to={`/${detectLang(navigator.languages)}/activate`} replace /> },
  {
    path: "/:lang",
    element: <LangLayout />,
    children: [
      { index: true, element: <Navigate to="activate" replace /> },
      { path: "activate", element: <ActivatePage /> },
      // Post-activation area: wrapped by the License guard; on detecting revocation/deletion → kick back to activate.
      {
        element: <RequireLicense />,
        children: [
          { path: "login", element: <LoginGate /> },
          // Protected subtree: redirects to /<lang>/login when not logged in.
          {
            element: <RequireAuth />,
            children: [
              // Forced password-change page / setup wizard: reachable once logged in (not gated by RequireSetup, otherwise an infinite loop).
              { path: "change-password", element: <ChangePasswordPage /> },
              { path: "wizard", element: <WizardPage /> },
              // Console: requires the first-login password change to be completed first (RequireSetup).
              {
                element: <RequireSetup />,
                children: [
                  {
                    path: "admin",
                    element: <AdminLayout />,
                    children: [
                      { index: true, element: <OverviewPage /> },
                      { path: "workspaces", element: <WorkspacesPage /> },
                      { path: "members", element: <MembersPage /> },
                      { path: "knowledge-bases", element: <KbOverviewPage /> },
                      { path: "channels", element: <ChannelsPage /> },
                      { path: "audit-logs", element: <AuditLogsPage /> },
                      { path: "branding", element: <BrandingSettingsPage /> },
                      {
                        path: "settings",
                        children: [
                          { index: true, element: <Navigate to="operators" replace /> },
                          { path: "operators", element: <SystemUsersPage /> },
                          { path: "email", element: <EmailSettingsPage /> },
                          { path: "login", element: <LoginSettingsPage /> },
                          { path: "password", element: <PasswordSettingsPage /> },
                          { path: "license", element: <LicenseSettingsPage /> },
                        ],
                      },
                      {
                        path: "account",
                        children: [
                          { index: true, element: <Navigate to="password" replace /> },
                          { path: "password", element: <EditPasswordPage /> },
                        ],
                      },
                    ],
                  },
                ],
              },
            ],
          },
        ],
      },
      { path: "*", element: <Navigate to="activate" replace /> },
    ],
  },
]);
