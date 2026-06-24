/** 视口懒加载的逐页 WebP 版面图查看器(类 PDF 阅读器)。
 *  每页占位 div 按容器宽度 ×(h/w) 预先撑开高度防 CLS;
 *  IntersectionObserver(rootMargin 提前 ~1.5 屏)进入视口附近才挂 <img>,离开很远卸载省内存。 */
import { useEffect, useRef, useState } from "react";

import { sourcePageUrl, type SourcePage } from "@/lib/kb";

function LazyPage({
  kbId, sourceId, page, containerWidth, root,
}: {
  kbId: string; sourceId: string; page: SourcePage; containerWidth: number; root: HTMLElement | null;
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

  // 按容器宽度等比预撑开高度,避免加载抖动。
  const ratio = page.w > 0 ? page.h / page.w : 1.414;
  const minHeight = containerWidth > 0 ? Math.round(containerWidth * ratio) : undefined;

  return (
    <div
      ref={ref}
      className="mx-auto w-full max-w-3xl overflow-hidden rounded-md bg-surface shadow-sm ring-1 ring-border/40"
      style={{ minHeight }}
    >
      {visible ? (
        <img
          src={sourcePageUrl(kbId, sourceId, page.n)}
          alt={`page ${page.n}`}
          loading="lazy"
          width={page.w || undefined}
          height={page.h || undefined}
          className="block h-auto w-full"
        />
      ) : null}
    </div>
  );
}

export function LazyPageViewer({
  kbId, sourceId, pages,
}: {
  kbId: string; sourceId: string; pages: SourcePage[];
}) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  const [root, setRoot] = useState<HTMLElement | null>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    setRoot(el);
    const ro = new ResizeObserver((entries) => {
      for (const ent of entries) setWidth(ent.contentRect.width);
    });
    ro.observe(el);
    setWidth(el.clientWidth);
    return () => ro.disconnect();
  }, []);

  // 占位估宽:max-w-3xl(48rem≈768px),减去左右内边距。
  const innerWidth = Math.min(width - 32, 768);

  return (
    <div ref={scrollRef} className="h-full overflow-y-auto bg-canvas p-4">
      <div className="space-y-4">
        {pages.map((p) => (
          <LazyPage
            key={p.n}
            kbId={kbId}
            sourceId={sourceId}
            page={p}
            containerWidth={innerWidth}
            root={root}
          />
        ))}
      </div>
    </div>
  );
}
