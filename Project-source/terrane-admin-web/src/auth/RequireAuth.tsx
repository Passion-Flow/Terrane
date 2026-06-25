/** Protected route guard — adapted for data routers (wrapper component + Outlet).
 *  loading: show a loading placeholder (avoids a redirect flash before the initial /me returns);
 *  not logged in: redirect to /<lang>/login; logged in: render the subtree (Outlet). */

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
