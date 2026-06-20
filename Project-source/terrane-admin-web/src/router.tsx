/** 路由 —— URL 路径式 i18n（i18n.md：所有页带 /<lang>/ 前缀，根路径按浏览器语言 302）。
 *  公开：activate（免登录，锁定态贴 License 解锁，反死锁关键）。
 *  License 守卫区（RequireLicense，轮询吊销/删除 → 踢回 activate）：
 *    login（已登录则跳 /admin）；RequireAuth → /admin 管理控制台。 */

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
  // changeLanguage 触发 i18next 订阅更新，不能在渲染期执行（React 渲染期 setState 限制）
  useEffect(() => {
    if (lang && isSupported(lang)) applyLang(lang);
  }, [lang]);
  if (!valid) {
    return <Navigate to={`/${detectLang(navigator.languages)}/activate`} replace />;
  }
  return <Outlet />;
}

/** 登录页守卫：已登录访问 /login 直接跳 /admin。 */
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
      // 激活后区域：License 守卫包裹，轮询到吊销/删除 → 踢回 activate。
      {
        element: <RequireLicense />,
        children: [
          { path: "login", element: <LoginGate /> },
          // 受保护子树：未登录重定向 /<lang>/login。
          {
            element: <RequireAuth />,
            children: [
              // 强制改密页 / 初始化向导：已登录可达（不被 RequireSetup 拦，否则死循环）。
              { path: "change-password", element: <ChangePasswordPage /> },
              { path: "wizard", element: <WizardPage /> },
              // 控制台：须先完成首登改密（RequireSetup）。
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
