/** Workspace top bar — logo + language/theme + user + sign out. Shared by the KB list and detail views. */

import { SignOut, User } from "@phosphor-icons/react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams } from "react-router";

import { useAuth } from "@/auth/AuthContext";
import { LanguageSelect } from "@/components/LanguageSelect";
import { Logo } from "@/components/Logo";
import { ThemeToggle } from "@/components/ThemeToggle";
import { FALLBACK_LANG, isSupported } from "@/i18n/langs";

export function AppHeader() {
  const { t } = useTranslation();
  const { lang } = useParams();
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const seg = lang && isSupported(lang) ? lang : FALLBACK_LANG;

  async function onLogout() {
    await logout();
    navigate(`/${seg}/login`, { replace: true });
  }

  return (
    <header className="flex items-center justify-between border-b border-border/70 px-8 py-4">
      <Link to={`/${seg}/`} className="transition-opacity hover:opacity-80"><Logo /></Link>
      <div className="flex items-center gap-2.5">
        <LanguageSelect />
        <ThemeToggle />
        <span aria-hidden="true" className="h-5 w-px bg-border" />
        <span className="flex items-center gap-1.5 text-sm text-ink-secondary">
          <User className="size-4" />
          {user?.username ?? user?.email}
        </span>
        <button type="button" onClick={onLogout}
          className="flex items-center gap-1.5 rounded-(--radius-control) border border-border px-3 py-1.5 text-sm text-ink-secondary transition hover:bg-canvas hover:text-ink">
          <SignOut className="size-4" />
          {t("home.logout")}
        </button>
      </div>
    </header>
  );
}
