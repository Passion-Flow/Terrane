/** Setup wizard guard — above the console, inside RequireAuth:
 *  1) Forced first-login password change (must_change_password) → password-change page;
 *  2) Super admin with an incomplete wizard → wizard page (non-super-admins are not gated: the wizard API returns 403 for them, and the wizard is a super-admin first-run responsibility).
 *  /change-password and /wizard themselves do not carry this guard (otherwise an infinite loop). */

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
  // Query wizard status only for super admins who have passed the password-change step (skip for non-super-admins / when the change is incomplete).
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
