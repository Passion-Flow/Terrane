/** 源「整页」预览(非弹窗):左 = 原文版面(逐页 WebP 懒加载 / 回退 OriginalPreview),
 *  右 = 解析结果(Markdown)。render_status 为 pending/rendering 时轮询 /pages 直到 done。 */
import { ArrowLeft, DownloadSimple } from "@phosphor-icons/react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router";

import { LazyPageViewer } from "@/components/LazyPageViewer";
import { Markdown } from "@/components/ui/Markdown";
import { OriginalPreview } from "@/components/OriginalPreview";
import { FALLBACK_LANG, isSupported } from "@/i18n/langs";
import { ApiError } from "@/lib/api";
import {
  getSource, getSourcePages, sourceOriginalUrl,
  type KbSourceDetail, type SourcePage,
} from "@/lib/kb";

export function SourcePreviewPage() {
  const { t } = useTranslation();
  const { lang, kbId, sourceId } = useParams();
  const navigate = useNavigate();
  const seg = lang && isSupported(lang) ? lang : FALLBACK_LANG;
  const kb = kbId ?? "";
  const sid = sourceId ?? "";

  const [detail, setDetail] = useState<KbSourceDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [pages, setPages] = useState<SourcePage[]>([]);
  const [renderStatus, setRenderStatus] = useState<string | null>(null);

  const pollRef = useRef<number | null>(null);

  const loadPages = useCallback(async () => {
    try {
      const r = await getSourcePages(kb, sid);
      setRenderStatus(r.status);
      if (r.status === "done" && r.page_count > 0) {
        setPages(r.pages);
        if (pollRef.current) { window.clearTimeout(pollRef.current); pollRef.current = null; }
        return;
      }
      if (r.status === "pending" || r.status === "rendering") {
        pollRef.current = window.setTimeout(() => { void loadPages(); }, 2500);
      }
    } catch { /* ignore — 回退到 OriginalPreview */ }
  }, [kb, sid]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    (async () => {
      try {
        const d = await getSource(kb, sid);
        if (cancelled) return;
        setDetail(d);
        setRenderStatus(d.render_status ?? null);
        const rs = d.render_status;
        if (rs === "done" && (d.page_count ?? 0) > 0) {
          void loadPages();
        } else if (rs === "pending" || rs === "rendering") {
          void loadPages();
        }
      } catch (e) {
        if (cancelled) return;
        if (e instanceof ApiError && (e.status === 404 || e.status === 403)) setNotFound(true);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
      if (pollRef.current) { window.clearTimeout(pollRef.current); pollRef.current = null; }
    };
  }, [kb, sid, loadPages]);

  const goBack = () => navigate(`/${seg}/kb/${kb}`);

  if (notFound) {
    return (
      <main className="flex min-h-[70vh] items-center justify-center">
        <div className="text-center">
          <p className="text-sm text-ink-secondary">{t("kb.notFound")}</p>
          <button onClick={goBack} className="mt-3 text-sm text-accent hover:underline">{t("kb.back")}</button>
        </div>
      </main>
    );
  }

  const isRendering = renderStatus === "pending" || renderStatus === "rendering";
  const hasPages = renderStatus === "done" && pages.length > 0;
  const canDownload = detail?.has_original;

  return (
    <div className="flex h-[calc(100vh-3.5rem)] min-h-0 flex-col">
      {/* 顶栏 */}
      <header className="flex shrink-0 items-center gap-3 border-b border-border/60 px-5 py-3">
        <button onClick={goBack} title={t("kb.back")}
          className="flex shrink-0 items-center gap-1 rounded-(--radius-control) px-2 py-1 text-sm text-ink-secondary transition hover:bg-canvas hover:text-ink">
          <ArrowLeft className="size-4" /> <span className="hidden sm:inline">{t("kb.back")}</span>
        </button>
        <div className="min-w-0 flex-1">
          <p className="line-clamp-1 text-sm font-semibold text-ink">{detail?.title ?? "…"}</p>
          <p className="mt-0.5 line-clamp-1 text-[11px] text-ink-faint">
            {detail ? t(`kb.status.${detail.status}`, { defaultValue: detail.status }) : ""}
            {detail?.mime ? ` · ${detail.mime}` : ""}
            {detail ? ` · ${t("kb.chunks", { n: detail.chunk_count })}` : ""}
          </p>
        </div>
        {canDownload && (
          <a href={sourceOriginalUrl(kb, sid)} download={detail?.title}
            className="flex shrink-0 items-center gap-1.5 rounded-(--radius-control) border border-border px-3 py-1.5 text-sm text-ink-secondary transition hover:bg-canvas hover:text-ink">
            <DownloadSimple className="size-4" /> <span className="hidden sm:inline">{t("source.downloadOriginal")}</span>
          </a>
        )}
      </header>

      {/* 主体:左右分栏(窄屏上下堆叠) */}
      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-2">
        {/* 左:原文版面 */}
        <section className="flex min-h-0 flex-col border-b border-border/60 lg:border-b-0 lg:border-e">
          <div className="shrink-0 border-b border-border/40 px-4 py-1.5 text-[11px] font-medium text-ink-faint">{t("source.originalLayout")}</div>
          <div className="min-h-0 flex-1">
            {loading ? (
              <div className="flex h-full items-center justify-center text-xs text-ink-faint">{t("common.loading")}</div>
            ) : hasPages ? (
              <LazyPageViewer kbId={kb} sourceId={sid} pages={pages} />
            ) : isRendering ? (
              <div className="flex h-full flex-col items-center justify-center gap-3 text-ink-faint">
                <span className="size-6 animate-spin rounded-full border-2 border-border border-t-accent" />
                <p className="text-sm">{t("source.generatingLayout")}</p>
              </div>
            ) : detail?.has_original ? (
              <div className="h-full overflow-auto bg-canvas">
                <OriginalPreview kbId={kb} sourceId={sid} mime={detail.mime} title={detail.title} />
              </div>
            ) : (
              <div className="flex h-full items-center justify-center text-xs text-ink-faint">{t("source.noOriginal")}</div>
            )}
          </div>
        </section>

        {/* 右:解析结果 */}
        <section className="flex min-h-0 flex-col">
          <div className="shrink-0 border-b border-border/40 px-4 py-1.5 text-[11px] font-medium text-ink-faint">{t("source.parsedResult")}</div>
          <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
            {loading ? (
              <div className="space-y-2">{[...Array(8)].map((_, i) => <div key={i} className="h-3.5 animate-pulse rounded bg-canvas" style={{ width: `${95 - i * 6}%` }} />)}</div>
            ) : detail?.error ? (
              <p className="text-sm text-danger">{detail.error}</p>
            ) : detail?.parsed_text.trim() ? (
              <Markdown>{detail.parsed_text}</Markdown>
            ) : (
              <p className="py-10 text-center text-sm text-ink-faint">{t("kb.previewEmpty")}</p>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
