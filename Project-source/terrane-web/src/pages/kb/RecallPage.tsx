/** Recall test subpage —— Retrieval 2.0: Fast/Deep/Auto routing over vector + lexical + tree-reasoning +
 *  graph multi-hop, with score bars and an explainable "document > section > page" citation path. */

import { FileText, Lightning, MagnifyingGlass, TreeStructure } from "@phosphor-icons/react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";

import { useKb } from "@/components/KbLayout";
import { searchKb, type RetrievalMode, type SearchHit } from "@/lib/kb";

export function RecallPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { id, seg } = useKb();

  const [q, setQ] = useState("");
  const [mode, setMode] = useState<RetrievalMode>("auto");
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const [effMode, setEffMode] = useState<string>("");
  const [searching, setSearching] = useState(false);

  async function onSearch(e?: React.FormEvent) {
    e?.preventDefault();
    if (!q.trim()) { setHits(null); return; }
    setSearching(true);
    try {
      const r = await searchKb(id, q.trim(), undefined, mode);
      setHits(r.hits); setEffMode(r.mode || "");
    } finally { setSearching(false); }
  }

  const field = "w-full rounded-(--radius-control) border border-border bg-canvas px-3 py-2 text-sm text-ink outline-none focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/30";
  const MODES: { k: RetrievalMode; label: string }[] = [
    { k: "auto", label: t("kb.modeAuto") }, { k: "fast", label: t("kb.modeFast") }, { k: "deep", label: t("kb.modeDeep") },
  ];

  return (
    <div className="px-6 py-8 sm:px-8">
      <div className="mx-auto max-w-4xl">
        <h1 className="text-2xl font-bold tracking-tight text-ink">{t("kbNav.recall")}</h1>
        <p className="mt-1 text-sm text-ink-secondary">{t("kbPages.recallSubtitle")}</p>

        <form onSubmit={onSearch} className="mt-6 flex flex-wrap items-center gap-2">
          <div className="relative min-w-0 flex-1">
            <MagnifyingGlass className="absolute start-3 top-1/2 size-4 -translate-y-1/2 text-ink-faint" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("kb.searchPlaceholder")} className={`${field} ps-9`} />
          </div>
          {/* Retrieval mode toggle */}
          <div className="flex shrink-0 rounded-(--radius-control) border border-border bg-canvas p-0.5">
            {MODES.map((m) => (
              <button key={m.k} type="button" onClick={() => setMode(m.k)}
                className={`whitespace-nowrap rounded-[7px] px-2.5 py-1.5 text-xs font-medium transition ${
                  mode === m.k ? "bg-accent text-white" : "text-ink-secondary hover:text-ink"}`}>
                {m.label}
              </button>
            ))}
          </div>
          <button type="submit" disabled={searching} className="shrink-0 rounded-(--radius-control) bg-accent px-4 py-2 text-sm font-medium text-white transition hover:bg-accent-hover disabled:opacity-50">
            {searching ? t("kb.searching") : t("kb.search")}
          </button>
        </form>
        <p className="mt-2 text-[11px] leading-snug text-ink-faint">{t("kb.modeHint")}</p>

        <div className="mt-4">
          {hits === null ? (
            <p className="py-12 text-center text-sm text-ink-faint">{t("kb.searchHint")}</p>
          ) : hits.length === 0 ? (
            <p className="py-12 text-center text-sm text-ink-faint">{t("kb.noHits")}</p>
          ) : (
            <div className="space-y-3">
              <p className="flex items-center gap-2 text-xs text-ink-faint">
                {t("kb.hitsCount", { n: hits.length })}
                {effMode && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-accent-soft px-2 py-0.5 text-[11px] font-medium text-accent">
                    {effMode === "deep" ? <TreeStructure className="size-3" /> : <Lightning className="size-3" weight="fill" />}
                    {effMode === "deep" ? t("kb.modeDeep") : t("kb.modeFast")}
                  </span>
                )}
              </p>
              {hits.map((h) => {
                const pct = Math.max(4, Math.min(100, Math.round(h.score * 100)));
                const path = (h.citation_path || []).filter(Boolean);
                const pages = h.page_start ? (h.page_end && h.page_end !== h.page_start ? `p.${h.page_start}–${h.page_end}` : `p.${h.page_start}`) : "";
                return (
                  <button key={h.chunk_id} onClick={() => navigate(`/${seg}/kb/${id}/source/${h.source_id}`)}
                    className="block w-full rounded-xl border border-border/70 bg-surface/40 p-4 text-start transition hover:-translate-y-0.5 hover:border-accent/50 hover:bg-surface hover:shadow-sm">
                    <div className="flex items-center justify-between gap-2 text-xs text-ink-faint">
                      <span className="flex min-w-0 items-center gap-1"><FileText className="size-3.5 shrink-0" /> <span className="truncate">{h.source_title}</span></span>
                      <span className="flex shrink-0 items-center gap-1.5">
                        <span className="h-1.5 w-16 overflow-hidden rounded-full bg-canvas">
                          <span className="block h-full rounded-full bg-accent" style={{ width: `${pct}%` }} />
                        </span>
                        <span className="text-accent">{pct}%</span>
                      </span>
                    </div>
                    {/* Explainable citation path (Deep mode) */}
                    {(path.length > 0 || pages) && (
                      <div className="mt-1.5 flex flex-wrap items-center gap-1 text-[11px] text-ink-faint">
                        {path.length > 0 && <span className="truncate text-accent/80">{path.join(" › ")}</span>}
                        {pages && <span className="shrink-0 rounded bg-canvas px-1.5 py-0.5">{pages}</span>}
                      </div>
                    )}
                    <p className="mt-2 line-clamp-4 whitespace-pre-wrap text-[13px] leading-relaxed text-ink-secondary">{h.content}</p>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
