/** Knowledge Wiki (a compounding projection of the knowledge base). Owner/editor can "compile the Wiki"
 *  (async backend + progress bar + polling + resume-on-refresh); rendered with the project's Markdown component (tables/code/formulas). */

import { BookOpen, Sparkle } from "@phosphor-icons/react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { Markdown } from "@/components/ui/Markdown";
import { ApiError } from "@/lib/api";
import { compileWiki, getWikiPage, wikiStatus } from "@/lib/kb";

export function KbWiki({ kbId, canEdit }: { kbId: string; canEdit: boolean }) {
  const { t } = useTranslation();
  const [body, setBody] = useState<string | null>(null);
  const [updated, setUpdated] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);
  const [failed, setFailed] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const pollRef = useRef<number | null>(null);

  const load = useCallback(async () => {
    try { const p = await getWikiPage(kbId, "overview"); setBody(p.body_md); setUpdated(p.updated_at); }
    catch (e) { if (e instanceof ApiError && e.status === 404) setBody(null); }
    finally { setLoaded(true); }
  }, [kbId]);

  const stopPoll = useCallback(() => { if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; } }, []);
  const startPoll = useCallback(() => {
    if (pollRef.current) return;
    pollRef.current = window.setInterval(async () => {
      try {
        const s = await wikiStatus(kbId);
        setProgress(s.progress);
        if (s.status === "done") { stopPoll(); setBusy(false); setFailed(false); await load(); }
        else if (s.status === "failed" || s.status === "none") { stopPoll(); setBusy(false); setFailed(s.status === "failed"); }
      } catch { /* ignore transient errors, keep polling */ }
    }, 2000);
  }, [kbId, load, stopPoll]);

  // On mount: fetch status once — if running, resume progress + polling (so a refresh keeps following), otherwise fetch the result page
  useEffect(() => {
    let alive = true;
    wikiStatus(kbId)
      .then((s) => {
        if (!alive) return;
        if (s.status === "running") { setBusy(true); setProgress(s.progress); startPoll(); }
        else { setFailed(s.status === "failed"); void load(); }
      })
      .catch(() => { if (alive) void load(); });
    return () => { alive = false; stopPoll(); };
  }, [kbId, load, startPoll, stopPoll]);

  async function compile() {
    setBusy(true); setProgress(0); setFailed(false);
    try {
      const r = await compileWiki(kbId);
      if (r.status === "running") startPoll();
      else { setBusy(false); if (r.body_md) { setBody(r.body_md); setUpdated(r.updated_at ?? null); } else await load(); }
    } catch { setBusy(false); setFailed(true); }
  }

  return (
    <div className="rounded-xl border border-border/70 bg-surface/40">
      <div className="flex items-center justify-between border-b border-border/50 px-5 py-3">
        <span className="flex items-center gap-1.5 text-sm font-medium text-ink">
          <BookOpen className="size-4 text-accent" weight="duotone" /> {t("kb.wikiTitle")}
          {updated && !busy && <span className="ms-1 text-xs font-normal text-ink-faint">· {t("kb.wikiUpdated")}</span>}
        </span>
        {canEdit && (
          <button onClick={compile} disabled={busy} className="flex items-center gap-1.5 rounded-full bg-accent px-3 py-1.5 text-xs font-medium text-white transition hover:bg-accent-hover disabled:opacity-50">
            <Sparkle className={`size-3.5 ${busy ? "animate-pulse" : ""}`} /> {busy ? `${t("kb.wikiCompiling")} ${progress}%` : body ? t("kb.wikiRecompile") : t("kb.wikiCompile")}
          </button>
        )}
      </div>

      {busy && (
        <div className="px-5 pt-4">
          <div className="mb-1.5 flex items-center justify-between text-xs text-ink-secondary">
            <span>{t("kb.wikiCompiling")}</span><span>{progress}%</span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-canvas">
            <div className="h-full rounded-full bg-accent transition-all duration-500" style={{ width: `${Math.max(5, progress)}%` }} />
          </div>
        </div>
      )}
      {failed && !busy && (
        <p className="px-5 pt-4 text-xs text-danger">{t("kb.wikiFailed")}</p>
      )}

      {body ? (
        <article className="max-w-none px-5 py-4"><Markdown>{body}</Markdown></article>
      ) : !busy ? (
        <div className="flex h-[360px] flex-col items-center justify-center text-center">
          <BookOpen className="size-10 text-ink-faint" weight="duotone" />
          <p className="mt-3 text-sm text-ink-secondary">{loaded ? t("kb.wikiEmpty") : t("common.loading")}</p>
        </div>
      ) : (
        <div className="flex h-[300px] flex-col items-center justify-center text-center">
          <Sparkle className="size-10 animate-pulse text-accent" weight="duotone" />
          <p className="mt-3 text-sm text-ink-secondary">{t("kb.wikiCompilingHint")}</p>
        </div>
      )}
    </div>
  );
}
