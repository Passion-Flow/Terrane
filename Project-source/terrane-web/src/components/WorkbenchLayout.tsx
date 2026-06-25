/** Frontend workbench shell (SaaS) —— collapsible left sidebar (Overview / Knowledge Bases / Knowledge Graph / Memory / Chat / expandable Settings group)
 *  + top bar (activation badge + light/dark toggle + avatar dropdown menu) + avatar/name at the bottom of the sidebar → profile modal. */

import {
  Books, Brain, CaretRight, ChatCircleText, Cpu, Gear, Graph, Key, type Icon,
  ShieldCheck, SidebarSimple, SignOut, SquaresFour, Translate, UserCircle,
} from "@phosphor-icons/react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { NavLink, Outlet, useLocation, useNavigate, useParams } from "react-router";

import { useAuth } from "@/auth/AuthContext";
import { Logo } from "@/components/Logo";
import { ProfileModal } from "@/components/ProfileModal";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Avatar } from "@/components/ui/Avatar";
import { Select } from "@/components/ui/Select";
import { FALLBACK_LANG, SUPPORTED_LANGS, isSupported } from "@/i18n/langs";
import { applyLang } from "@/i18n";
import { getLicenseStatus, type LicenseStatus } from "@/lib/license";

const LANG_LABEL: Record<string, string> = { "zh-CN": "简体中文", en: "English" };

export function WorkbenchLayout() {
  const { t } = useTranslation();
  const { lang } = useParams();
  const navigate = useNavigate();
  const loc = useLocation();
  const { user, logout } = useAuth();
  const seg = lang && isSupported(lang) ? lang : FALLBACK_LANG;

  const [collapsed, setCollapsed] = useState(() => localStorage.getItem("trn_nav_collapsed") === "1");
  const [settingsOpen, setSettingsOpen] = useState(() => loc.pathname.includes("/settings"));
  const [profileOpen, setProfileOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [lic, setLic] = useState<LicenseStatus | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => { localStorage.setItem("trn_nav_collapsed", collapsed ? "1" : "0"); }, [collapsed]);
  useEffect(() => { getLicenseStatus().then(setLic).catch(() => setLic(null)); }, []);
  useEffect(() => {
    if (!menuOpen) return;
    const h = (e: MouseEvent) => { if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, [menuOpen]);

  const onLogout = useCallback(async () => { await logout(); navigate(`/${seg}/login`, { replace: true }); }, [logout, navigate, seg]);

  const NAV: { to: string; icon: Icon; label: string; end?: boolean }[] = [
    { to: `/${seg}/`, icon: SquaresFour, label: t("nav.overview"), end: true },
    { to: `/${seg}/kb`, icon: Books, label: t("nav.kbs") },
    { to: `/${seg}/graph`, icon: Graph, label: t("nav.graph") },
    { to: `/${seg}/memory`, icon: Brain, label: t("nav.memory") },
    { to: `/${seg}/chat`, icon: ChatCircleText, label: t("nav.chat") },
  ];
  const SETTINGS: { to: string; icon: Icon; label: string }[] = [
    { to: `/${seg}/settings/models`, icon: Cpu, label: t("nav.modelSettings") },
    { to: `/${seg}/settings/security`, icon: ShieldCheck, label: t("nav.security") },
  ];

  const navCls = ({ isActive }: { isActive: boolean }) =>
    `group/n relative flex items-center gap-3 rounded-(--radius-control) px-3 py-2 text-sm font-medium transition active:translate-y-px ${
      isActive ? "bg-accent-soft text-accent" : "text-ink-secondary hover:bg-canvas hover:text-ink"} ${collapsed ? "justify-center" : ""}`;

  const W = collapsed ? "w-[4.25rem]" : "w-60";
  const active = (lic?.status === "active" || lic?.status === "expiring");
  // Open-source build (gating disabled) hides the activation badge; only shown when gating is enabled (required !== false).
  const showLicenseBadge = lic != null && lic.required !== false;

  return (
    <div className="flex min-h-screen bg-canvas">
      <aside className={`${W} flex shrink-0 flex-col border-e border-border/70 bg-surface/40 transition-[width] duration-200`}>
        <div className={`flex items-center gap-2 px-4 py-4 ${collapsed ? "justify-center" : "justify-between"}`}>
          {!collapsed && <Logo />}
          <button type="button" onClick={() => setCollapsed((v) => !v)} title={t("nav.collapse")}
            className="rounded-lg p-1.5 text-ink-faint transition hover:bg-canvas hover:text-ink">
            <SidebarSimple className="size-[18px]" />
          </button>
        </div>

        <nav className="flex-1 space-y-1 overflow-y-auto px-3 pb-3">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end} className={navCls} title={collapsed ? n.label : undefined}>
              <n.icon className="size-[18px] shrink-0" /> {!collapsed && n.label}
            </NavLink>
          ))}

          {/* Settings (expandable group) */}
          <button type="button" onClick={() => { if (collapsed) { setCollapsed(false); setSettingsOpen(true); } else setSettingsOpen((v) => !v); }}
            className={`flex w-full items-center gap-3 rounded-(--radius-control) px-3 py-2 text-sm font-medium text-ink-secondary transition hover:bg-canvas hover:text-ink ${collapsed ? "justify-center" : ""}`} title={collapsed ? t("nav.settings") : undefined}>
            <Gear className="size-[18px] shrink-0" />
            {!collapsed && <><span className="flex-1 text-start">{t("nav.settings")}</span><CaretRight className={`size-3.5 transition ${settingsOpen ? "rotate-90" : ""}`} /></>}
          </button>
          {!collapsed && settingsOpen && (
            <div className="ms-3 space-y-1 border-s border-border/60 ps-2.5">
              {SETTINGS.map((s) => (
                <NavLink key={s.to} to={s.to} className={({ isActive }) => `flex items-center gap-2.5 rounded-(--radius-control) px-2.5 py-1.5 text-[13px] transition ${isActive ? "text-accent" : "text-ink-secondary hover:text-ink"}`}>
                  <s.icon className="size-4 shrink-0" /> {s.label}
                </NavLink>
              ))}
            </div>
          )}
        </nav>

      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center justify-end gap-2.5 border-b border-border/70 bg-surface/30 px-6">
          {/* Activation badge —— only shown when gating is enabled */}
          {showLicenseBadge && (
            <span className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${active ? "bg-success/10 text-success" : "bg-danger-soft text-danger"}`}>
              <span className={`size-1.5 rounded-full ${active ? "bg-success" : "bg-danger"}`} />
              {active ? t("topbar.activated") : t("topbar.inactive")}
            </span>
          )}
          <ThemeToggle />
          {/* Avatar dropdown menu */}
          <div ref={menuRef} className="relative">
            <button type="button" onClick={() => setMenuOpen((v) => !v)} className="rounded-full ring-2 ring-transparent transition hover:ring-border">
              <Avatar src={user?.avatar} name={user?.username} email={user?.email} size={32} />
            </button>
            {menuOpen && (
              <div className="absolute end-0 z-50 mt-2 w-60 overflow-hidden rounded-(--radius-card) border border-border bg-surface shadow-xl">
                <div className="border-b border-border/60 px-4 py-3">
                  <p className="truncate text-sm font-medium text-ink">{user?.username ?? "—"}</p>
                  <p className="truncate text-xs text-ink-faint">{user?.email}</p>
                </div>
                <div className="p-1.5">
                  <MenuItem icon={UserCircle} label={t("menu.profile")} onClick={() => { setMenuOpen(false); setProfileOpen(true); }} />
                  <div className="flex items-center justify-between gap-2 rounded-(--radius-control) px-2.5 py-1.5">
                    <span className="flex items-center gap-2.5 text-[13px] text-ink-secondary"><Translate className="size-4" /> {t("menu.language")}</span>
                    <Select size="sm" className="w-28" value={seg}
                      options={SUPPORTED_LANGS.map((l) => ({ value: l, label: LANG_LABEL[l] ?? l }))}
                      onChange={(v) => { applyLang(v); navigate(loc.pathname.replace(/^\/[^/]+/, `/${v}`)); }} />
                  </div>
                  <MenuItem icon={Key} label={t("menu.changePassword")} onClick={() => { setMenuOpen(false); navigate(`/${seg}/settings/security`); }} />
                  <MenuItem icon={ShieldCheck} label={t("menu.security")} onClick={() => { setMenuOpen(false); navigate(`/${seg}/settings/security`); }} />
                  <div className="my-1 border-t border-border/60" />
                  <MenuItem icon={SignOut} label={t("home.logout")} danger onClick={onLogout} />
                </div>
              </div>
            )}
          </div>
        </header>
        <main className="min-w-0 flex-1 overflow-y-auto"><Outlet /></main>
      </div>

      <ProfileModal open={profileOpen} onClose={() => setProfileOpen(false)} />
    </div>
  );
}

function MenuItem({ icon: Ic, label, onClick, danger }: { icon: Icon; label: string; onClick: () => void; danger?: boolean }) {
  return (
    <button type="button" onClick={onClick}
      className={`flex w-full items-center gap-2.5 rounded-(--radius-control) px-2.5 py-1.5 text-start text-[13px] transition hover:bg-canvas ${danger ? "text-danger hover:text-danger" : "text-ink-secondary hover:text-ink"}`}>
      <Ic className="size-4 shrink-0" /> {label}
    </button>
  );
}
