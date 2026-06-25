/** Overview — SaaS dashboard: stat cards + recent knowledge bases + quick start. */

import { Books, Brain, ChatCircleText, Plus, Sparkle } from "@phosphor-icons/react";
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router";

import { useAuth } from "@/auth/AuthContext";
import { PageHeader } from "@/components/ui/PageHeader";
import { FALLBACK_LANG, isSupported } from "@/i18n/langs";
import { listKbs, type Kb } from "@/lib/kb";
import { listMemories } from "@/lib/memory";

export function OverviewPage() {
  const { t } = useTranslation();
  const { lang } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const seg = lang && isSupported(lang) ? lang : FALLBACK_LANG;

  const [kbs, setKbs] = useState<Kb[] | null>(null);
  const [memCount, setMemCount] = useState<number | null>(null);

  const load = useCallback(async () => {
    try { setKbs((await listKbs()).items); } catch { setKbs([]); }
    try { setMemCount((await listMemories()).items.length); } catch { setMemCount(0); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const stats = [
    { icon: Books, label: t("nav.kbs"), value: kbs?.length, to: `/${seg}/kb` },
    { icon: Brain, label: t("nav.memory"), value: memCount, to: `/${seg}/memory` },
    { icon: ChatCircleText, label: t("nav.chat"), value: null, to: `/${seg}/chat` },
  ];

  return (
    <div className="px-8 py-10">
      <div className="mx-auto max-w-6xl">
        <PageHeader title={t("overview.hello", { name: user?.username ?? user?.email ?? "" })} subtitle={t("overview.subtitle")} />

        <div className="mt-7 grid grid-cols-1 gap-4 sm:grid-cols-3">
          {stats.map((s) => (
            <button key={s.label} onClick={() => navigate(s.to)}
              className="group flex items-center gap-4 rounded-(--radius-card) border border-border/70 bg-surface/40 p-5 text-start transition active:translate-y-px hover:-translate-y-0.5 hover:border-accent/50 hover:shadow-md">
              <span className="flex size-11 items-center justify-center rounded-xl bg-accent-soft transition group-hover:bg-accent"><s.icon className="size-5 text-accent transition group-hover:text-white" weight="duotone" /></span>
              <span>
                <span className="block text-2xl font-semibold tabular-nums text-ink">{s.value ?? "—"}</span>
                <span className="block text-[13px] text-ink-secondary">{s.label}</span>
              </span>
            </button>
          ))}
        </div>

        {/* Quick start */}
        <div className="mt-4 flex flex-wrap gap-2.5">
          <button onClick={() => navigate(`/${seg}/kb`)} className="flex items-center gap-1.5 rounded-full bg-accent px-4 py-2 text-sm font-medium text-white transition active:translate-y-px hover:bg-accent-hover"><Plus className="size-4" weight="bold" /> {t("kb.create")}</button>
          <button onClick={() => navigate(`/${seg}/chat`)} className="flex items-center gap-1.5 rounded-full border border-border px-4 py-2 text-sm font-medium text-ink-secondary transition hover:bg-canvas hover:text-ink"><Sparkle className="size-4" /> {t("overview.startChat")}</button>
        </div>

        {/* Recent knowledge bases */}
        <h2 className="mt-9 mb-3 text-sm font-semibold text-ink">{t("overview.recent")}</h2>
        {kbs === null ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">{[...Array(3)].map((_, i) => <div key={i} className="h-28 animate-pulse rounded-(--radius-card) border border-border/60 bg-surface/40" />)}</div>
        ) : kbs.length === 0 ? (
          <div className="rounded-(--radius-card) border border-dashed border-border bg-surface/30 py-14 text-center text-sm text-ink-secondary">{t("kb.empty")}</div>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {kbs.slice(0, 6).map((kb) => (
              <button key={kb.id} onClick={() => navigate(`/${seg}/kb/${kb.id}`)}
                className="group flex flex-col rounded-(--radius-card) border border-border/70 bg-surface/40 p-4 text-start transition active:translate-y-px hover:-translate-y-0.5 hover:border-accent/50 hover:shadow-md">
                <span className="flex items-center gap-2"><Books className="size-[18px] text-accent" weight="duotone" /><span className="line-clamp-1 text-sm font-medium text-ink group-hover:text-accent">{kb.name}</span></span>
                <span className="mt-2 line-clamp-2 min-h-[2.25rem] text-[13px] text-ink-secondary">{kb.description || t("kb.noDesc")}</span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
