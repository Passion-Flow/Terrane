/** 初始化向导守卫 —— 控制台之上、RequireAuth 之内：
 *  ① 首登强制改密（must_change_password）→ 改密页；
 *  ② 超管且向导未完成 → 向导页（非超管不拦：wizard 接口对其 403，向导是超管首启职责）。
 *  /change-password 与 /wizard 自身不挂本守卫（否则死循环）。 */

import { useQuery } from "@tanstack/react-query";
import { Navigate, Outlet, useParams } from "react-router";
import { useTranslation } from "react-i18next";

import { useAuth } from "@/auth/AuthContext";
import { FALLBACK_LANG, isSupported } from "@/i18n/langs";
import { getWizard } from "@/lib/wizard";

export function RequireSetup() {
  const { user } = useAuth();
  const { lang } = useParams();
  const { t } = useTranslation();
  const seg = lang && isSupported(lang) ? lang : FALLBACK_LANG;

  const isSuper = !!user && (user.role === "super_admin" || user.permissions.includes("*"));
  const needPwChange = !!user?.must_change_password;
  // 仅超管、且已过改密步时查询向导状态（非超管 / 改密未完成不查）。
  const { data: wiz, isLoading } = useQuery({
    queryKey: ["wizard"],
    queryFn: getWizard,
    enabled: isSuper && !needPwChange,
  });

  if (needPwChange) {
    return <Navigate to={`/${seg}/change-password`} replace />;
  }
  if (isSuper) {
    if (isLoading) {
      return (
        <div className="flex min-h-screen items-center justify-center text-sm text-ink-secondary">
          {t("common.loading")}
        </div>
      );
    }
    if (wiz && !wiz.completed) {
      return <Navigate to={`/${seg}/wizard`} replace />;
    }
  }
  return <Outlet />;
}
