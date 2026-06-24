/** 管理控制台外壳 —— 侧栏导航 + 顶栏（语言/主题/用户/登出）+ 内容区 Outlet。
 *  导航 label 走 i18n。已实现：概览 / 审计日志；其余模块占位（soon），随阶段填充。
 *  响应式：lg 固定侧栏，小屏抽屉。 */

import {
  Books,
  Buildings,
  CaretDown,
  CaretUp,
  Certificate,
  EnvelopeSimple,
  Gear,
  List,
  LockKey,
  Palette,
  Password,
  Plugs,
  Scroll,
  ShieldCheck,
  SignIn,
  SignOut,
  SquaresFour,
  UserGear,
  UsersThree,
  type Icon,
} from "@phosphor-icons/react";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { NavLink, Outlet, useLocation, useNavigate, useParams } from "react-router";

import { useAuth } from "@/auth/AuthContext";
import { LanguageSelect } from "@/components/LanguageSelect";
import { Logo } from "@/components/Logo";
import { ThemeToggle } from "@/components/ThemeToggle";
import { FALLBACK_LANG, isSupported } from "@/i18n/langs";
import { getLicenseCard } from "@/lib/license";

interface NavItem {
  to: string;
  labelKey: string;
  icon: Icon;
  end?: boolean;
  soon?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { to: "", labelKey: "admin.nav.overview", icon: SquaresFour, end: true },
  { to: "workspaces", labelKey: "admin.nav.workspaces", icon: Buildings },
  { to: "members", labelKey: "admin.nav.members", icon: UsersThree },
  { to: "knowledge-bases", labelKey: "admin.nav.knowledgeBases", icon: Books },
  { to: "channels", labelKey: "admin.nav.channels", icon: Plugs },
  { to: "audit-logs", labelKey: "admin.nav.auditLogs", icon: Scroll },
  { to: "branding", labelKey: "admin.nav.branding", icon: Palette },
];

// 可展开分组——子项各自独立成页（对齐 Dify）。会长子功能的领域都成组,随阶段增加子项。
interface NavGroupDef { basePath: string; labelKey: string; icon: Icon; children: NavItem[] }

const NAV_GROUPS: NavGroupDef[] = [
  {
    basePath: "settings", labelKey: "admin.nav.settings", icon: Gear,
    children: [
      { to: "settings/operators", labelKey: "settings.nav.operators", icon: UserGear },
      { to: "settings/email", labelKey: "settings.nav.email", icon: EnvelopeSimple },
      { to: "settings/login", labelKey: "settings.nav.login", icon: SignIn },
      { to: "settings/password", labelKey: "settings.nav.password", icon: Password },
      { to: "settings/license", labelKey: "settings.nav.license", icon: Certificate },
    ],
  },
  {
    basePath: "account", labelKey: "admin.nav.account", icon: ShieldCheck,
    children: [
      { to: "account/password", labelKey: "account.nav.password", icon: LockKey },
    ],
  },
];

/** 可展开导航分组:父项点击展开/收起;进入任一子页自动展开 + 父项高亮。 */
function NavGroup({ navBase, group, onNavigate }: { navBase: string; group: NavGroupDef; onNavigate: () => void }) {
  const { t } = useTranslation();
  const { pathname } = useLocation();
  const groupActive = pathname.startsWith(`${navBase}/${group.basePath}`);
  const [open, setOpen] = useState(groupActive);
  useEffect(() => { if (groupActive) setOpen(true); }, [groupActive]);
  const GroupIcon = group.icon;

  return (
    <li>
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open}
        className={`flex w-full items-center gap-2.5 rounded-(--radius-control) px-3 py-2 text-sm transition-colors ${
          groupActive ? "font-medium text-accent" : "text-ink-secondary hover:bg-canvas hover:text-ink"}`}>
        <GroupIcon className="size-[18px] shrink-0" />
        {t(group.labelKey)}
        <CaretDown className={`ms-auto size-3.5 shrink-0 transition-transform ${open ? "" : "-rotate-90"}`} />
      </button>
      {open && (
        <ul className="mt-0.5 space-y-0.5 ps-3.5">
          {group.children.map((c) => (
            <li key={c.to}>
              <NavLink to={`${navBase}/${c.to}`} onClick={onNavigate}
                className={({ isActive }) =>
                  `flex items-center gap-2.5 rounded-(--radius-control) px-3 py-1.5 text-[13px] transition-colors ${
                    isActive ? "bg-accent-soft font-medium text-accent"
                      : "text-ink-secondary hover:bg-canvas hover:text-ink"}`}>
                <c.icon className="size-4 shrink-0" />
                {t(c.labelKey)}
              </NavLink>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

/** 底部可折叠用户菜单 —— 头像首字母 + 邮箱/角色，点击向上展开角色 + 退出登录；点击外部收起。 */
function SidebarUser({ email, role, onLogout, logoutLabel }: {
  email: string; role: string; onLogout: () => void; logoutLabel: string;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const h = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, [open]);
  const initial = (email.trim()[0] ?? "?").toUpperCase();

  return (
    <div ref={ref} className="relative border-t border-border/70 px-3 py-3">
      {open && (
        <div className="absolute inset-x-3 bottom-full mb-1.5 overflow-hidden rounded-(--radius-control) border border-border bg-surface py-1 shadow-lg">
          <p className="px-3 py-1.5 text-[11px] font-medium uppercase tracking-wide text-ink-faint">
            {role}
          </p>
          <button type="button" onClick={onLogout}
            className="flex w-full items-center gap-2 px-3 py-2 text-[13px] text-ink-secondary transition-colors hover:bg-canvas hover:text-ink">
            <SignOut className="size-4 shrink-0" />
            {logoutLabel}
          </button>
        </div>
      )}
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open}
        className="flex w-full items-center gap-2.5 rounded-(--radius-control) px-2 py-1.5 transition-colors hover:bg-canvas">
        <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-accent-soft text-xs font-semibold text-accent">
          {initial}
        </span>
        <span className="min-w-0 flex-1 text-start">
          <span className="block truncate text-[13px] text-ink" title={email}>{email}</span>
          <span className="block truncate text-[11px] text-ink-faint">{role}</span>
        </span>
        <CaretUp className={`size-3.5 shrink-0 text-ink-faint transition-transform ${open ? "" : "rotate-180"}`} />
      </button>
    </div>
  );
}

export function AdminLayout() {
  const { t } = useTranslation();
  const { lang } = useParams();
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const seg = lang && isSupported(lang) ? lang : FALLBACK_LANG;
  const [drawer, setDrawer] = useState(false);
  const navBase = `/${seg}/admin`;

  // 开源版（门控关闭）隐藏 License 设置导航项（页面 URL 仍可达）。
  const { data: licenseCard } = useQuery({ queryKey: ["license"], queryFn: getLicenseCard });
  const licenseOff = licenseCard?.required === false;
  const navGroups: NavGroupDef[] = licenseOff
    ? NAV_GROUPS.map((g) =>
        g.basePath === "settings"
          ? { ...g, children: g.children.filter((c) => c.to !== "settings/license") }
          : g,
      )
    : NAV_GROUPS;

  async function onLogout() {
    await logout();
    navigate(`/${seg}/login`, { replace: true });
  }

  const sidebar = (
    <nav className="flex h-full flex-col bg-surface">
      <div className="flex h-14 items-center border-b border-border/70 px-4">
        <Logo />
      </div>
      <ul className="flex-1 space-y-0.5 overflow-y-auto px-2.5 py-3">
        {NAV_ITEMS.map((item) =>
          item.soon ? (
            <li key={item.to || "overview"}>
              <span aria-disabled="true"
                className="flex cursor-not-allowed items-center gap-2.5 rounded-(--radius-control) px-3 py-2 text-sm text-ink-faint/70">
                <item.icon className="size-[18px] shrink-0" />
                {t(item.labelKey)}
                <span className="ms-auto rounded-full bg-canvas px-1.5 py-0.5 text-[10px] text-ink-faint">
                  {t("admin.soon")}
                </span>
              </span>
            </li>
          ) : (
            <li key={item.to || "overview"}>
              <NavLink to={item.to ? `${navBase}/${item.to}` : navBase} end={item.end}
                onClick={() => setDrawer(false)}
                className={({ isActive }) =>
                  `flex items-center gap-2.5 rounded-(--radius-control) px-3 py-2 text-sm transition-colors ${
                    isActive ? "bg-accent-soft font-medium text-accent"
                      : "text-ink-secondary hover:bg-canvas hover:text-ink"}`}>
                <item.icon className="size-[18px] shrink-0" />
                {t(item.labelKey)}
              </NavLink>
            </li>
          ),
        )}
        {navGroups.map((g) => (
          <NavGroup key={g.basePath} navBase={navBase} group={g} onNavigate={() => setDrawer(false)} />
        ))}
      </ul>
      <SidebarUser email={user?.email ?? ""}
        role={user ? t(`admin.roles.${user.role}`, { defaultValue: user.role }) : "—"}
        onLogout={onLogout} logoutLabel={t("admin.logout")} />
    </nav>
  );

  return (
    <div className="flex min-h-[100dvh] bg-canvas text-ink">
      <aside className="hidden w-60 shrink-0 border-e border-border/70 lg:block">
        <div className="sticky top-0 h-[100dvh]">{sidebar}</div>
      </aside>

      {drawer && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button type="button" aria-label="close" onClick={() => setDrawer(false)}
            className="absolute inset-0 bg-ink/30" />
          <div className="absolute inset-y-0 start-0 w-64 border-e border-border shadow-lg">{sidebar}</div>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-border/70 bg-canvas/90 px-4 backdrop-blur sm:px-6">
          <button type="button" aria-label="menu" onClick={() => setDrawer(true)}
            className="flex size-9 items-center justify-center rounded-(--radius-control) text-ink-secondary hover:bg-surface hover:text-ink lg:hidden">
            <List className="size-5" />
          </button>
          <span className="hidden lg:block" />
          <div className="flex items-center gap-2.5">
            <LanguageSelect />
            <ThemeToggle />
          </div>
        </header>
        <main className="flex-1 px-4 py-6 sm:px-6 lg:px-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
