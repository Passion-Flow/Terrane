/** 受保护路由守卫 —— 适配数据路由（包装组件 + Outlet）。
 *  loading：显加载占位（避免首屏 /me 未回前闪重定向）；
 *  未登录：重定向到 /<lang>/login；已登录：渲染子树（Outlet）。 */

import { Navigate, Outlet, useParams } from "react-router";
import { useTranslation } from "react-i18next";

import { useAuth } from "@/auth/AuthContext";
import { FALLBACK_LANG, isSupported } from "@/i18n/langs";

export function RequireAuth() {
  const { user, loading } = useAuth();
  const { lang } = useParams();
  const { t } = useTranslation();
  const seg = lang && isSupported(lang) ? lang : FALLBACK_LANG;

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-ink-secondary">
        {t("common.loading")}
      </div>
    );
  }
  if (!user) {
    return <Navigate to={`/${seg}/login`} replace />;
  }
  return <Outlet />;
}
