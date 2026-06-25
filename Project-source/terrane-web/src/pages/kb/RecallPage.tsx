/** Recall test subpage —— hybrid vector-semantic + lexical retrieval, with score bars. */

import { FileText, MagnifyingGlass } from "@phosphor-icons/react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";

import { useKb } from "@/components/KbLayout";
import { searchKb, type SearchHit } from "@/lib/kb";

export function RecallPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { id, seg } = useKb();

  const [q, setQ] = useState("");
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const [searching, setSearching] = useState(false);

  async function onSearch(e?: React.FormEvent) {
    e?.preventDefault();
    if (!q.trim()) { setHits(null); return; }
    setSearching(true);
    try { setHits((await searchKb(id, q.trim())).hits); } finally { setSearching(false); }
  }

  const field = "w-full rounded-(--radius-control) border border-border bg-canvas px-3 py-2 text-sm text-ink outline-none focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/30";

  return (
    <div className="px-6 py-8 sm:px-8">
      <div className="mx-auto max-w-4xl">
        <h1 className="text-2xl font-bold tracking-tight text-ink">{t("kbNav.recall")}</h1>
        <p className="mt-1 text-sm text-ink-secondary">{t("kbPages.recallSubtitle")}</p>

        <form onSubmit={onSearch} className="mt-6 flex items-center gap-2">
          <div className="relative flex-1">
            <MagnifyingGlass className="absolute start-3 top-1/2 size-4 -translate-y-1/2 text-ink-faint" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("kb.searchPlaceholder")} className={`${field} ps-9`} />
          </div>
          <button type="submit" disabled={searching} className="rounded-(--radius-control) bg-accent px-4 py-2 text-sm font-medium text-white transition hover:bg-accent-hover disabled:opacity-50">
            {searching ? t("kb.searching") : t("kb.search")}
          </button>
        </form>

        <div className="mt-4">
          {hits === null ? (
            <p className="py-12 text-center text-sm text-ink-faint">{t("kb.searchHint")}</p>
          ) : hits.length === 0 ? (
            <p className="py-12 text-center text-sm text-ink-faint">{t("kb.noHits")}</p>
          ) : (
            <div className="space-y-3">
              <p className="text-xs text-ink-faint">{t("kb.hitsCount", { n: hits.length })}</p>
              {hits.map((h) => {
                const pct = Math.max(4, Math.min(100, Math.round(h.score * 100)));
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
