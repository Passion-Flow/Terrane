/** 源「整页」预览(非弹窗)。两种模式:
 *  - 对话:整宽,基于本文档的 RAG 问答(DocumentSourceChat)。
 *  - 解析对比:左 = 原文版面(逐页 WebP 懒加载 / 回退 OriginalPreview),右 = 解析结果(Markdown)。
 *  版面图渐进消费:render_status 为 pending/rendering 时每 ~2s 轮询 /pages,把逐步增长的 pages 喂给 LazyPageViewer。 */
import { ArrowLeft, ChatCircleText, Columns, DownloadSimple } from "@phosphor-icons/react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router";

import { LazyPageViewer, type LazyPageViewerHandle } from "@/components/LazyPageViewer";
import { DocumentSourceChat } from "@/components/DocumentSourceChat";
import { Markdown } from "@/components/ui/Markdown";
import { OriginalPreview } from "@/components/OriginalPreview";
import { FALLBACK_LANG, isSupported } from "@/i18n/langs";
import { ApiError } from "@/lib/api";
import {
  getSource, getSourcePages, sourceOriginalUrl,
  type ChatSource, type KbSourceDetail, type SourcePage,
} from "@/lib/kb";

type Mode = "chat" | "compare";

export function SourcePreviewPage() {
  const { t } = useTranslation();
  const { lang, kbId, sourceId } = useParams();
  const navigate = useNavigate();
  const seg = lang && isSupported(lang) ? lang : FALLBACK_LANG;
  const kb = kbId ?? "";
  const sid = sourceId ?? "";

  const [mode, setMode] = useState<Mode>("chat");
  const [detail, setDetail] = useState<KbSourceDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [pages, setPages] = useState<SourcePage[]>([]);
  const [pageCount, setPageCount] = useState(0);
  const [renderStatus, setRenderStatus] = useState<string | null>(null);

  const pollRef = useRef<number | null>(null);
  const viewerRef = useRef<LazyPageViewerHandle>(null);

  const stopPoll = () => { if (pollRef.current) { window.clearTimeout(pollRef.current); pollRef.current = null; } };

  const loadPages = useCallback(async () => {
    try {
      const r = await getSourcePages(kb, sid);
      setRenderStatus(r.status);
      setPageCount(r.page_count);
      // 渐进:始终消费当前已返回的 pages(rendering 期间会逐步增长)。
      if (r.pages?.length) setPages(r.pages);
      if (r.status === "pending" || r.status === "rendering") {
        pollRef.current = window.setTimeout(() => { void loadPages(); }, 2000);
      } else {
        stopPoll();
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
        setPageCount(d.page_count ?? 0);
        const rs = d.render_status;
        if (rs === "done" || rs === "pending" || rs === "rendering") void loadPages();
      } catch (e) {
        if (cancelled) return;
        if (e instanceof ApiError && (e.status === 404 || e.status === 403)) setNotFound(true);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; stopPoll(); };
  }, [kb, sid, loadPages]);

  const goBack = () => navigate(`/${seg}/kb/${kb}`);

  // 点引用 → 切到解析对比,并尝试滚动到对应页(若引用切片带页码语义可扩展;暂滚到首屏)。
  const onCite = useCallback((_s: ChatSource) => {
    setMode("compare");
  }, []);

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
  const hasRenderedPages = pages.length > 0 || (renderStatus === "done" && pageCount > 0);
  const canDownload = detail?.has_original;

  return (
    <div className="flex h-[calc(100vh-3.5rem)] min-h-0 flex-col">
      {/* 顶栏 */}
      <header className="flex shrink-0 flex-wrap items-center gap-3 border-b border-border/60 px-5 py-3">
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

        {/* 分段控件:对话 / 解析对比 */}
        <div className="flex shrink-0 items-center rounded-(--radius-control) bg-canvas p-0.5 ring-1 ring-border/60">
          {([
            { k: "chat" as const, icon: <ChatCircleText className="size-4" />, label: t("source.modeChat") },
            { k: "compare" as const, icon: <Columns className="size-4" />, label: t("source.modeCompare") },
          ]).map((m) => (
            <button key={m.k} onClick={() => setMode(m.k)} aria-pressed={mode === m.k}
              className={`flex items-center gap-1.5 whitespace-nowrap rounded-(--radius-control) px-3 py-1.5 text-sm font-medium transition ${
                mode === m.k ? "bg-surface text-ink shadow-sm ring-1 ring-border/50" : "text-ink-secondary hover:text-ink"
              }`}>
              {m.icon} <span className="hidden sm:inline">{m.label}</span>
            </button>
          ))}
        </div>

        {canDownload && (
          <a href={sourceOriginalUrl(kb, sid)} download={detail?.title}
            className="flex shrink-0 items-center gap-1.5 rounded-(--radius-control) border border-border px-3 py-1.5 text-sm text-ink-secondary transition hover:bg-canvas hover:text-ink">
            <DownloadSimple className="size-4" /> <span className="hidden sm:inline">{t("source.downloadOriginal")}</span>
          </a>
        )}
      </header>

      {/* 主体 */}
      {mode === "chat" ? (
        <div className="min-h-0 flex-1">
          <DocumentSourceChat kbId={kb} sourceId={sid} onCite={onCite} />
        </div>
      ) : (
        <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-2">
          {/* 左:原文版面 */}
          <section className="flex min-h-0 flex-col border-b border-border/60 lg:border-b-0 lg:border-e">
            <div className="flex shrink-0 items-center justify-between gap-2 border-b border-border/40 px-4 py-1.5 text-[11px] font-medium text-ink-faint">
              <span>{t("source.originalLayout")}</span>
              {isRendering && pageCount > 0 && (
                <span className="flex items-center gap-1.5 text-accent">
                  <span className="size-3 animate-spin rounded-full border-2 border-border border-t-accent" />
                  {t("source.generatedProgress", { x: pages.length, y: pageCount })}
                </span>
              )}
            </div>
            <div className="min-h-0 flex-1">
              {loading ? (
                <div className="flex h-full items-center justify-center text-xs text-ink-faint">{t("common.loading")}</div>
              ) : hasRenderedPages ? (
                <LazyPageViewer ref={viewerRef} kbId={kb} sourceId={sid} pages={pages} pageCount={pageCount} />
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
      )}
    </div>
  );
}
