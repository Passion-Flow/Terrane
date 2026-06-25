/** KB overview subpage — stats grid + health score + actionable suggestions (reuses /lint). */

import {
  ArrowsClockwise, ChartBar, FileText, Graph as GraphIcon, Sparkle, TextT, type Icon,
} from "@phosphor-icons/react";
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { lintKb, type KbLint } from "@/lib/kb";
import { useKb } from "@/components/KbLayout";

export function OverviewPage() {
  const { t } = useTranslation();
  const { id, sources } = useKb();
  const [lint, setLint] = useState<KbLint | null>(null);

  const loadStats = useCallback(async () => {
    try { setLint(await lintKb(id)); } catch { /* ignore */ }
  }, [id]);
  useEffect(() => { void loadStats(); }, [loadStats, sources.length]);

  return (
    <div className="px-6 py-8 sm:px-8">
      <div className="mx-auto max-w-5xl">
        <h1 className="text-2xl font-bold tracking-tight text-ink">{t("kbNav.overview")}</h1>
        <p className="mt-1 text-sm text-ink-secondary">{t("kbPages.overviewSubtitle")}</p>
        <div className="mt-6"><Overview lint={lint} onRetry={loadStats} /></div>
      </div>
    </div>
  );
}

function Overview({ lint, onRetry }: { lint: KbLint | null; onRetry: () => void }) {
  const { t } = useTranslation();
  if (!lint) {
    return (
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {[...Array(5)].map((_, i) => <div key={i} className="h-24 animate-pulse rounded-xl border border-border/60 bg-surface/40" />)}
      </div>
    );
  }
  const s = lint.stats;
  const cards: { label: string; value: number | string; icon: Icon }[] = [
    { label: t("kb.ovSources"), value: s.sources, icon: FileText },
    { label: t("kb.ovChunks"), value: s.chunks, icon: TextT },
    { label: t("kb.ovEmbeds"), value: s.embedded_chunks, icon: Sparkle },
    { label: t("kb.ovGraphNodes"), value: s.graph_nodes, icon: GraphIcon },
    { label: t("kb.ovHealth"), value: `${lint.score}`, icon: ChartBar },
  ];
  const scoreColor = lint.score >= 80 ? "text-accent" : lint.score >= 50 ? "text-ink" : "text-danger";
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {cards.map((c) => {
          const Ic = c.icon;
          const isScore = c.label === t("kb.ovHealth");
          return (
            <div key={c.label} className="rounded-xl border border-border/70 bg-surface/40 p-4">
              <div className="flex items-center gap-1.5 text-xs text-ink-faint"><Ic className="size-4" /> {c.label}</div>
              <p className={`mt-2 text-2xl font-semibold tabular-nums ${isScore ? scoreColor : "text-ink"}`}>{c.value}</p>
            </div>
          );
        })}
        <div className="rounded-xl border border-border/70 bg-surface/40 p-4">
          <div className="flex items-center gap-1.5 text-xs text-ink-faint"><FileText className="size-4" /> Wiki</div>
          <p className="mt-2 text-sm font-medium text-ink">{s.has_wiki ? t("kb.ovWiki") : t("kb.ovWikiNo")}</p>
        </div>
      </div>

      <div className="rounded-xl border border-border/70 bg-surface/40 p-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-ink">{t("kb.ovIssues")}</h3>
          <button onClick={onRetry} className="rounded p-1 text-ink-faint transition hover:text-ink" title={t("common.retry")}><ArrowsClockwise className="size-3.5" /></button>
        </div>
        {lint.issues.length === 0 ? (
          <p className="mt-3 text-[13px] text-ink-secondary">{t("kb.ovNoIssues")}</p>
        ) : (
          <ul className="mt-3 space-y-2">
            {lint.issues.map((iss, i) => (
              <li key={i} className="flex items-start gap-2 text-[13px]">
                <span className={`mt-0.5 size-1.5 shrink-0 rounded-full ${iss.level === "warn" || iss.level === "error" ? "bg-danger" : "bg-accent"}`} />
                <span className="text-ink-secondary">{
                  iss.code === "failed_sources" ? t("kb.lint.failed_sources", { n: s.failed_sources })
                    : iss.code === "unembedded" ? t("kb.lint.unembedded", { n: s.chunks - s.embedded_chunks, total: s.chunks })
                      : t(`kb.lint.${iss.code}`, { defaultValue: iss.msg })
                }</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
