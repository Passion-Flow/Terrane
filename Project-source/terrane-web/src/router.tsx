/** 前台路由 —— URL 路径式 i18n。License 守卫（锁定态 LockedPage）；
 *  公开认证页（login/register/forgot/reset/verify）；受保护工作台首页（RequireAuth）。 */

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

/** 已登录访问登录/注册 → 跳工作台。 */
function GuestOnly({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const { lang } = useParams();
  const seg = lang && isSupported(lang) ? lang : detectLang(navigator.languages);
  if (!loading && user) return <Navigate to={`/${seg}/`} replace />;
  return <>{children}</>;
}

/** 无语言前缀的邮件链接（/verify-email、/reset-password）→ 补上浏览器语言前缀并保留 query。
 *  邮件里的链接做成语言无关，前端在此解析语言（否则 /verify-email 会被当作 :lang 而丢掉 token）。 */
function LangRedirect({ to }: { to: string }) {
  const seg = detectLang(navigator.languages);
  return <Navigate to={`/${seg}/${to}${window.location.search}`} replace />;
}

export const router = createBrowserRouter([
  { path: "/", element: <Navigate to={`/${detectLang(navigator.languages)}/`} replace /> },
  // 邮件链接（无语言前缀）补前缀 + 保留 ?token=，避免被 /:lang 吞掉。
  { path: "/verify-email", element: <LangRedirect to="verify-email" /> },
  { path: "/reset-password", element: <LangRedirect to="reset-password" /> },
  {
    path: "/:lang",
    element: <LangLayout />,
    children: [
      // License 守卫：锁定态全程落 LockedPage。
      {
        element: <RequireLicense />,
        children: [
          { path: "login", element: <GuestOnly><LoginPage /></GuestOnly> },
          { path: "register", element: <GuestOnly><RegisterPage /></GuestOnly> },
          { path: "forgot-password", element: <ForgotPasswordPage /> },
          { path: "reset-password", element: <ResetPasswordPage /> },
          { path: "verify-email", element: <VerifyEmailPage /> },
          // 受保护工作台。
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
              // 知识库外壳（Dify 式 IA）：进入某个库 → 左侧变库功能导航，子页独立。
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
              // 源整页预览（不带库侧栏，自带返回）。
              { path: "kb/:kbId/source/:sourceId", element: <SourcePreviewPage /> },
            ],
          },
        ],
      },
      { path: "*", element: <Navigate to="." replace /> },
    ],
  },
]);
