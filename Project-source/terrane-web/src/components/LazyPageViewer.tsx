/** 视口懒加载的逐页 WebP 版面图查看器(类 PDF 阅读器),支持「渐进消费」+ 大文档窗口化。
 *  - 每页占位 div 按容器宽度 ×(h/w) 预先撑开高度防 CLS;
 *  - IntersectionObserver(rootMargin 提前 ~1.5 屏)进入视口附近才挂 <img>,离开很远卸载省内存;
 *  - 渐进:pageCount 已知但 pages 里还没该页时,显示「渲染中」骨架占位;
 *  - 大文档(slot 数 > WINDOW_THRESHOLD)按滚动位置窗口化,只挂窗口内 slot 的 DOM,避免几百节点。 */
import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { sourcePageUrl, type SourcePage } from "@/lib/kb";

export interface LazyPageViewerHandle {
  /** 滚动到指定页码(1-based),平滑居中。 */
  scrollToPage: (n: number) => void;
}

const WINDOW_THRESHOLD = 80;   // slot 数超过此值才启用窗口化
const WINDOW_OVERSCAN = 6;     // 窗口上下各多渲染的 slot 数
const DEFAULT_RATIO = 1.414;   // A4 纵向默认高宽比(占位用)

function LazyPage({
  kbId, sourceId, page, slotHeight, root, label,
}: {
  kbId: string; sourceId: string; page: SourcePage; slotHeight: number | undefined; root: HTMLElement | null; label: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      ([e]) => setVisible(e.isIntersecting),
      { root, rootMargin: "150% 0px", threshold: 0 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [root]);

  return (
    <div
      ref={ref}
      className="mx-auto w-full max-w-3xl overflow-hidden rounded-md bg-surface shadow-sm ring-1 ring-border/40"
      style={{ minHeight: slotHeight }}
    >
      {visible ? (
        <img
          src={sourcePageUrl(kbId, sourceId, page.n)}
          alt={label}
          loading="lazy"
          width={page.w || undefined}
          height={page.h || undefined}
          className="block h-auto w-full"
        />
      ) : null}
    </div>
  );
}

function PendingPage({ slotHeight, label }: { slotHeight: number | undefined; label: string }) {
  return (
    <div
      className="mx-auto flex w-full max-w-3xl items-center justify-center rounded-md bg-surface/60 shadow-sm ring-1 ring-border/40"
      style={{ minHeight: slotHeight }}
    >
      <div className="flex flex-col items-center gap-2 text-ink-faint">
        <span className="size-5 animate-spin rounded-full border-2 border-border border-t-accent" />
        <span className="text-[11px]">{label}</span>
      </div>
    </div>
  );
}

export const LazyPageViewer = forwardRef<LazyPageViewerHandle, {
  kbId: string;
  sourceId: string;
  pages: SourcePage[];
  /** 文档总页数(渐进:可能 > pages.length)。缺省时按 pages.length 计。 */
  pageCount?: number;
}>(function LazyPageViewer({ kbId, sourceId, pages, pageCount }, ref) {
  const { t } = useTranslation();
  const scrollRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  const [root, setRoot] = useState<HTMLElement | null>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [viewportH, setViewportH] = useState(0);

  // 已到达页 → 按页码索引,方便对 slot 取真实页。
  const byNum = useMemo(() => {
    const m = new Map<number, SourcePage>();
    for (const p of pages) m.set(p.n, p);
    return m;
  }, [pages]);

  const total = Math.max(pageCount ?? 0, pages.length);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    setRoot(el);
    const ro = new ResizeObserver((entries) => {
      for (const ent of entries) { setWidth(ent.contentRect.width); setViewportH(ent.contentRect.height); }
    });
    ro.observe(el);
    setWidth(el.clientWidth);
    setViewportH(el.clientHeight);
    return () => ro.disconnect();
  }, []);

  // 占位估宽:max-w-3xl(48rem≈768px),减去左右内边距。
  const innerWidth = Math.min(width - 32, 768);

  // 每个 slot 的预估高度(真实页用其比例,未到达页用默认 A4 比例)。
  const slotHeights = useMemo(() => {
    const arr: number[] = [];
    for (let i = 1; i <= total; i++) {
      const p = byNum.get(i);
      const ratio = p && p.w > 0 ? p.h / p.w : DEFAULT_RATIO;
      arr.push(innerWidth > 0 ? Math.round(innerWidth * ratio) : Math.round(700 * DEFAULT_RATIO));
    }
    return arr;
  }, [total, byNum, innerWidth]);

  const GAP = 16; // space-y-4
  // slot 的累计 top 偏移(含 padding-top 16)。
  const offsets = useMemo(() => {
    const arr: number[] = [];
    let acc = 16;
    for (let i = 0; i < slotHeights.length; i++) {
      arr.push(acc);
      acc += slotHeights[i] + GAP;
    }
    return arr;
  }, [slotHeights]);
  const totalHeight = (offsets[offsets.length - 1] ?? 16) + (slotHeights[slotHeights.length - 1] ?? 0) + 16;

  const windowed = total > WINDOW_THRESHOLD;

  // 窗口范围(仅窗口化时计算):二分找首个底部 >= scrollTop 的 slot。
  const [first, last] = useMemo(() => {
    if (!windowed || total === 0) return [0, total - 1];
    const vh = viewportH || 800;
    const topEdge = scrollTop;
    const botEdge = scrollTop + vh;
    let f = 0;
    while (f < total && offsets[f] + slotHeights[f] < topEdge) f++;
    let l = f;
    while (l < total && offsets[l] <= botEdge) l++;
    return [Math.max(0, f - WINDOW_OVERSCAN), Math.min(total - 1, l + WINDOW_OVERSCAN)];
  }, [windowed, total, scrollTop, viewportH, offsets, slotHeights]);

  const onScroll = useCallback(() => {
    if (windowed && scrollRef.current) setScrollTop(scrollRef.current.scrollTop);
  }, [windowed]);

  useImperativeHandle(ref, () => ({
    scrollToPage: (n: number) => {
      const idx = n - 1;
      const el = scrollRef.current;
      if (!el || idx < 0 || idx >= offsets.length) return;
      el.scrollTo({ top: Math.max(0, offsets[idx] - 24), behavior: "smooth" });
    },
  }), [offsets]);

  const renderSlot = (i: number) => {
    const n = i + 1;
    const p = byNum.get(n);
    return p ? (
      <LazyPage
        key={n} kbId={kbId} sourceId={sourceId} page={p}
        slotHeight={slotHeights[i]} root={root}
        label={t("source.pageLabel", { n })}
      />
    ) : (
      <PendingPage key={n} slotHeight={slotHeights[i]} label={t("source.pageRendering", { n })} />
    );
  };

  if (windowed) {
    const items = [];
    for (let i = first; i <= last; i++) {
      items.push(
        <div key={i + 1} style={{ position: "absolute", top: offsets[i], left: 0, right: 0 }}>
          {renderSlot(i)}
        </div>,
      );
    }
    return (
      <div ref={scrollRef} onScroll={onScroll} className="h-full overflow-y-auto bg-canvas px-4">
        <div style={{ position: "relative", height: totalHeight }}>{items}</div>
      </div>
    );
  }

  return (
    <div ref={scrollRef} className="h-full overflow-y-auto bg-canvas p-4">
      <div className="space-y-4">
        {Array.from({ length: total }, (_, i) => renderSlot(i))}
      </div>
    </div>
  );
});
