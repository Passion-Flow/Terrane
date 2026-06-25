/** Full-page source preview (not a modal). Persistent parse comparison:
 *  left = original layout (per-page WebP lazy loading / falls back to OriginalPreview), right = parsed result (Markdown).
 *  Bottom-right Q&A bubble → opens a draggable + resizable Q&A floating window (embeds DocumentSourceChat).
 *  Progressive layout-image consumption: while render_status is pending/rendering, poll /pages every ~2s. */
import { ArrowLeft, ChatCircleText, DownloadSimple, Minus, X } from "@phosphor-icons/react";
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
  type KbSourceDetail, type SourcePage,
} from "@/lib/kb";

// Floating window size/position constraints
const MIN_W = 300;
const MIN_H = 320;
const MARGIN = 16;

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
      if (r.pages?.length) setPages(r.pages);
      if (r.status === "pending" || r.status === "rendering") {
        pollRef.current = window.setTimeout(() => { void loadPages(); }, 2000);
      } else {
        stopPoll();
      }
    } catch { /* ignore — fall back to OriginalPreview */ }
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

  if (notFound) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-canvas">
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
    <div className="relative flex h-screen min-h-0 flex-col bg-canvas">
      {/* Top bar */}
      <header className="flex shrink-0 flex-wrap items-center gap-3 border-b border-border/60 bg-surface/30 px-5 py-3">
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

      {/* Body: persistent parse comparison */}
      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-2">
        {/* Left: original layout */}
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

        {/* Right: parsed result */}
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

      {/* Q&A floating window (bubble + draggable & resizable) */}
      <AskFloat kbId={kb} sourceId={sid} />
    </div>
  );
}

/** Bottom-right Q&A bubble → a draggable + resizable floating window. Implemented purely with front-end mouse events, no heavy dependencies. */
function AskFloat({ kbId, sourceId }: { kbId: string; sourceId: string }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [minimized, setMinimized] = useState(false);

  // Default bottom-right placement + size. Position expressed in left/top pixels (computed from the viewport's bottom-right corner on first open).
  const [box, setBox] = useState({ x: 0, y: 0, w: 400, h: 520, placed: false });
  const dragRef = useRef<{ mode: "move" | "resize"; px: number; py: number; bx: number; by: number; bw: number; bh: number } | null>(null);

  const clamp = useCallback((b: { x: number; y: number; w: number; h: number }) => {
    const vw = window.innerWidth, vh = window.innerHeight;
    const w = Math.min(Math.max(b.w, MIN_W), vw - MARGIN * 2);
    const h = Math.min(Math.max(b.h, MIN_H), vh - MARGIN * 2);
    const x = Math.min(Math.max(b.x, MARGIN), vw - w - MARGIN);
    const y = Math.min(Math.max(b.y, MARGIN), vh - h - MARGIN);
    return { x, y, w, h };
  }, []);

  // On open, if not yet placed, position it at the bottom-right corner.
  useEffect(() => {
    if (open && !box.placed) {
      const w = 400, h = 520;
      const x = window.innerWidth - w - MARGIN;
      const y = window.innerHeight - h - MARGIN;
      setBox({ ...clamp({ x, y, w, h }), placed: true });
    }
  }, [open, box.placed, clamp]);

  useEffect(() => {
    function onMove(e: MouseEvent) {
      const d = dragRef.current;
      if (!d) return;
      const dx = e.clientX - d.px, dy = e.clientY - d.py;
      if (d.mode === "move") {
        setBox((b) => ({ ...b, ...clamp({ x: d.bx + dx, y: d.by + dy, w: b.w, h: b.h }) }));
      } else {
        setBox((b) => ({ ...b, ...clamp({ x: b.x, y: b.y, w: d.bw + dx, h: d.bh + dy }) }));
      }
    }
    function onUp() { dragRef.current = null; document.body.style.userSelect = ""; }
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => { window.removeEventListener("mousemove", onMove); window.removeEventListener("mouseup", onUp); };
  }, [clamp]);

  const startMove = (e: React.MouseEvent) => {
    dragRef.current = { mode: "move", px: e.clientX, py: e.clientY, bx: box.x, by: box.y, bw: box.w, bh: box.h };
    document.body.style.userSelect = "none";
  };
  const startResize = (e: React.MouseEvent) => {
    e.stopPropagation();
    dragRef.current = { mode: "resize", px: e.clientX, py: e.clientY, bx: box.x, by: box.y, bw: box.w, bh: box.h };
    document.body.style.userSelect = "none";
  };

  if (!open) {
    return (
      <button onClick={() => setOpen(true)} title={t("source.askThisDoc")}
        className="fixed bottom-6 end-6 z-40 flex size-14 items-center justify-center rounded-full bg-accent text-white shadow-lg transition hover:bg-accent-hover hover:shadow-xl active:translate-y-px">
        <ChatCircleText className="size-7" weight="duotone" />
      </button>
    );
  }

  if (minimized) {
    return (
      <button onClick={() => setMinimized(false)} title={t("source.askThisDoc")}
        className="fixed bottom-6 end-6 z-40 flex items-center gap-2 rounded-full bg-accent px-4 py-2.5 text-sm font-medium text-white shadow-lg transition hover:bg-accent-hover active:translate-y-px">
        <ChatCircleText className="size-5" weight="duotone" /> {t("source.askThisDoc")}
      </button>
    );
  }

  return (
    <div className="fixed z-40 flex flex-col overflow-hidden rounded-(--radius-card) border border-border bg-surface shadow-2xl"
      style={{ left: box.x, top: box.y, width: box.w, height: box.h }}>
      {/* Title bar: draggable to reposition */}
      <div onMouseDown={startMove}
        className="flex shrink-0 cursor-move items-center justify-between gap-2 border-b border-border/60 bg-surface/80 px-3 py-2">
        <span className="flex min-w-0 items-center gap-1.5 text-[13px] font-medium text-ink">
          <ChatCircleText className="size-4 shrink-0 text-accent" weight="duotone" />
          <span className="truncate">{t("source.askThisDoc")}</span>
        </span>
        <div className="flex shrink-0 items-center gap-0.5">
          <button onMouseDown={(e) => e.stopPropagation()} onClick={() => setMinimized(true)} title={t("source.minimize")}
            className="rounded p-1 text-ink-faint transition hover:bg-canvas hover:text-ink"><Minus className="size-4" /></button>
          <button onMouseDown={(e) => e.stopPropagation()} onClick={() => setOpen(false)} title={t("common.close")}
            className="rounded p-1 text-ink-faint transition hover:bg-canvas hover:text-ink"><X className="size-4" /></button>
        </div>
      </div>

      {/* Content: document Q&A */}
      <div className="min-h-0 flex-1">
        <DocumentSourceChat kbId={kbId} sourceId={sourceId} />
      </div>

      {/* Bottom-right resize handle */}
      <div onMouseDown={startResize} title={t("source.resize")}
        className="absolute bottom-0 end-0 size-4 cursor-nwse-resize">
        <span className="absolute bottom-1 end-1 size-0 border-b-[7px] border-s-[7px] border-b-border border-s-transparent" />
      </div>
    </div>
  );
}
