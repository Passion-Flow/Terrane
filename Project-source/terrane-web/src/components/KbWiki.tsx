/** 知识 Wiki(知识复利投影)。owner/editor 可「编译 Wiki」;用项目 Markdown 组件渲染(表格/代码/公式)。 */

import { BookOpen, Sparkle } from "@phosphor-icons/react";
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { Markdown } from "@/components/ui/Markdown";
import { ApiError } from "@/lib/api";
import { compileWiki, getWikiPage } from "@/lib/kb";

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
    <div className="rounded-xl border border-border/70 bg-surface/40">
      <div className="flex items-center justify-between border-b border-border/50 px-5 py-3">
        <span className="flex items-center gap-1.5 text-sm font-medium text-ink">
          <BookOpen className="size-4 text-accent" weight="duotone" /> {t("kb.wikiTitle")}
          {updated && <span className="ms-1 text-xs font-normal text-ink-faint">· {t("kb.wikiUpdated")}</span>}
        </span>
        {canEdit && (
          <button onClick={compile} disabled={busy} className="flex items-center gap-1.5 rounded-full bg-accent px-3 py-1.5 text-xs font-medium text-white transition hover:bg-accent-hover disabled:opacity-50">
            <Sparkle className={`size-3.5 ${busy ? "animate-pulse" : ""}`} /> {busy ? t("kb.wikiCompiling") : body ? t("kb.wikiRecompile") : t("kb.wikiCompile")}
          </button>
        )}
      </div>
      {body ? (
        <article className="max-w-none px-5 py-4"><Markdown>{body}</Markdown></article>
      ) : (
        <div className="flex h-[360px] flex-col items-center justify-center text-center">
          <BookOpen className="size-10 text-ink-faint" weight="duotone" />
          <p className="mt-3 text-sm text-ink-secondary">{loaded ? t("kb.wikiEmpty") : t("common.loading")}</p>
        </div>
      )}
    </div>
  );
}
