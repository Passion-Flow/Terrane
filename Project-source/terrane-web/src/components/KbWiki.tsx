/** 知识 Wiki(知识复利投影)。owner/editor 可「编译 Wiki」;轻量 Markdown 渲染。 */

import { BookOpen, Sparkle } from "@phosphor-icons/react";
import { Fragment, type ReactNode, useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { ApiError } from "@/lib/api";
import { compileWiki, getWikiPage } from "@/lib/kb";

function inline(s: string): ReactNode {
  return s.split(/(\*\*[^*]+\*\*)/g).map((seg, i) =>
    seg.startsWith("**") && seg.endsWith("**")
      ? <strong key={i} className="font-semibold text-ink">{seg.slice(2, -2)}</strong>
      : <Fragment key={i}>{seg}</Fragment>);
}

function renderMarkdown(md: string): ReactNode[] {
  const out: ReactNode[] = [];
  let list: string[] = [];
  let key = 0;
  const flush = () => {
    if (list.length) {
      out.push(<ul key={key++} className="my-2 ms-5 list-disc space-y-1 text-[13px] text-ink-secondary">{list.map((it, i) => <li key={i}>{inline(it)}</li>)}</ul>);
      list = [];
    }
  };
  for (const ln of md.split("\n")) {
    if (/^### /.test(ln)) { flush(); out.push(<h3 key={key++} className="mt-4 text-sm font-semibold text-ink">{inline(ln.slice(4))}</h3>); }
    else if (/^## /.test(ln)) { flush(); out.push(<h2 key={key++} className="mt-5 border-b border-border/50 pb-1 text-base font-semibold text-ink">{inline(ln.slice(3))}</h2>); }
    else if (/^# /.test(ln)) { flush(); out.push(<h1 key={key++} className="mt-2 text-lg font-bold text-ink">{inline(ln.slice(2))}</h1>); }
    else if (/^\s*[-*] /.test(ln)) { list.push(ln.replace(/^\s*[-*] /, "")); }
    else if (ln.trim() === "") { flush(); }
    else { flush(); out.push(<p key={key++} className="my-2 text-[13px] leading-relaxed text-ink-secondary">{inline(ln)}</p>); }
  }
  flush();
  return out;
}

export function KbWiki({ kbId, canEdit }: { kbId: string; canEdit: boolean }) {
  const { t } = useTranslation();
  const [body, setBody] = useState<string | null>(null);
  const [updated, setUpdated] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(async () => {
    try { const p = await getWikiPage(kbId, "overview"); setBody(p.body_md); setUpdated(p.updated_at); }
    catch (e) { if (e instanceof ApiError && e.status === 404) setBody(null); }
    finally { setLoaded(true); }
  }, [kbId]);
  useEffect(() => { void load(); }, [load]);

  async function compile() {
    setBusy(true);
    try { const p = await compileWiki(kbId); if (p.body_md) { setBody(p.body_md); setUpdated(p.updated_at); } }
    finally { setBusy(false); }
  }

  return (
    <div className="rounded-xl border border-border/70 bg-surface/40 p-5">
      <div className="mb-3 flex items-center justify-between">
        <span className="text-sm font-medium text-ink">{t("kb.wikiTitle")}{updated && <span className="ms-2 text-xs text-ink-faint">{t("kb.wikiUpdated")}</span>}</span>
        {canEdit && (
          <button onClick={compile} disabled={busy} className="flex items-center gap-1.5 rounded-full bg-accent px-3 py-1.5 text-xs font-medium text-white hover:bg-accent-hover disabled:opacity-50">
            <Sparkle className="size-3.5" /> {busy ? t("kb.wikiCompiling") : body ? t("kb.wikiRecompile") : t("kb.wikiCompile")}
          </button>
        )}
      </div>
      {body ? (
        <article className="max-w-none">{renderMarkdown(body)}</article>
      ) : (
        <div className="flex h-[360px] flex-col items-center justify-center text-center">
          <BookOpen className="size-10 text-ink-faint" />
          <p className="mt-3 text-sm text-ink-secondary">{loaded ? t("kb.wikiEmpty") : t("common.loading")}</p>
        </div>
      )}
    </div>
  );
}
