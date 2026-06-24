/** 知识库外壳（Dify 式 IA）—— 进入某个库后,左侧变为「该库的功能导航」,
 *  取代全局工作台侧栏。顶部库图标+名称+描述 + 返回知识库；下方功能子页导航。
 *  KbLayout 拉一次 kb,通过 useOutletContext 把 kb + reload 共享给各子页,避免重复请求。 */

import {
  ArrowLeft, Books, ChartBar, ChatCircleText, FileText, Gear, MagnifyingGlass,
  PlugsConnected, Sparkle, type Icon,
} from "@phosphor-icons/react";
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { NavLink, Outlet, useNavigate, useOutletContext, useParams } from "react-router";

import { FALLBACK_LANG, isSupported } from "@/i18n/langs";
import { ApiError } from "@/lib/api";
import { getKb, listSources, type Kb, type KbSource } from "@/lib/kb";

export interface KbContext {
  kb: Kb | null;
  sources: KbSource[];
  reload: () => Promise<void>;
  reloadSources: () => Promise<void>;
  canEdit: boolean;
  id: string;
  seg: string;
}

/** 子页通过 useKb() 取共享 kb 信息。 */
export function useKb() {
  return useOutletContext<KbContext>();
}

export function KbLayout() {
  const { t } = useTranslation();
  const { lang, kbId } = useParams();
  const navigate = useNavigate();
  const seg = lang && isSupported(lang) ? lang : FALLBACK_LANG;
  const id = kbId ?? "";

  const [kb, setKb] = useState<Kb | null>(null);
  const [sources, setSources] = useState<KbSource[]>([]);
  const [notFound, setNotFound] = useState(false);

  const reloadSources = useCallback(async () => {
    try { setSources((await listSources(id)).items); } catch { /* ignore */ }
  }, [id]);

  const reload = useCallback(async () => {
    try {
      const [k, s] = await Promise.all([getKb(id), listSources(id)]);
      setKb(k); setSources(s.items);
    } catch (e) {
      if (e instanceof ApiError && (e.status === 404 || e.status === 403)) setNotFound(true);
    }
  }, [id]);
  useEffect(() => { void reload(); }, [reload]);

  const canEdit = kb?.my_role === "owner" || kb?.my_role === "editor";

  const NAV: { to: string; icon: Icon; label: string; end?: boolean }[] = [
    { to: `/${seg}/kb/${id}/overview`, icon: ChartBar, label: t("kbNav.overview") },
    { to: `/${seg}/kb/${id}/sources`, icon: FileText, label: t("kbNav.sources") },
    { to: `/${seg}/kb/${id}/studio`, icon: Sparkle, label: t("kbNav.studio") },
    { to: `/${seg}/kb/${id}/wiki`, icon: Books, label: t("kbNav.wiki") },
    { to: `/${seg}/kb/${id}/qa`, icon: ChatCircleText, label: t("kbNav.qa") },
    { to: `/${seg}/kb/${id}/recall`, icon: MagnifyingGlass, label: t("kbNav.recall") },
    { to: `/${seg}/kb/${id}/mcp`, icon: PlugsConnected, label: t("kbNav.mcp") },
    { to: `/${seg}/kb/${id}/settings`, icon: Gear, label: t("kbNav.settings") },
  ];

  const navCls = ({ isActive }: { isActive: boolean }) =>
    `group/n relative flex items-center gap-3 rounded-(--radius-control) px-3 py-2 text-sm font-medium transition active:translate-y-px ${
      isActive ? "bg-accent-soft text-accent" : "text-ink-secondary hover:bg-canvas hover:text-ink"}`;

  if (notFound) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-canvas">
        <div className="text-center">
          <p className="text-sm text-ink-secondary">{t("kb.notFound")}</p>
          <button onClick={() => navigate(`/${seg}/kb`)} className="mt-3 text-sm text-accent hover:underline">{t("kb.back")}</button>
        </div>
      </div>
    );
  }

  const ctx: KbContext = { kb, sources, reload, reloadSources, canEdit, id, seg };

  return (
    <div className="flex min-h-screen bg-canvas">
      <aside className="flex w-64 shrink-0 flex-col border-e border-border/70 bg-surface/40">
        <div className="px-4 py-4">
          <NavLink to={`/${seg}/kb`}
            className="flex items-center gap-1 text-[13px] text-ink-secondary transition hover:text-ink">
            <ArrowLeft className="size-4 shrink-0" /> {t("kbNav.back")}
          </NavLink>
          <div className="mt-4 flex items-start gap-2.5">
            <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-accent-soft">
              <Books className="size-5 text-accent" weight="duotone" />
            </span>
            <div className="min-w-0">
              <p className="line-clamp-1 text-[15px] font-semibold text-ink">{kb?.name ?? "…"}</p>
              {kb?.description && <p className="mt-0.5 line-clamp-2 text-[11px] leading-snug text-ink-faint">{kb.description}</p>}
            </div>
          </div>
        </div>

        <div className="mx-3 border-t border-border/60" />

        <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-3">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end} className={navCls}>
              <n.icon className="size-[18px] shrink-0" /> {n.label}
            </NavLink>
          ))}
        </nav>
      </aside>

      <main className="min-w-0 flex-1 overflow-y-auto"><Outlet context={ctx} /></main>
    </div>
  );
}
