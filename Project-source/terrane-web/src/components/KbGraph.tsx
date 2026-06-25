/** Knowledge graph visualization — react-force-graph-2d force-directed layout + zoom/drag/hover highlight + degree-based sizing, styled to the taste theme. */

import { ArrowsOut, Graph as GraphIcon, MagnifyingGlass, Sparkle } from "@phosphor-icons/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ForceGraph2D from "react-force-graph-2d";
import { useTranslation } from "react-i18next";

import { buildGraph, getGraph, graphStatus, type GraphEdge, type GraphNode } from "@/lib/kb";

const HEIGHT = 480;

/** Resolve a CSS variable into an rgb() color usable on the canvas. */
function cssColor(varName: string, fallback: string): string {
  try {
    const el = document.createElement("span");
    el.style.cssText = `color:var(${varName});position:absolute;visibility:hidden`;
    document.body.appendChild(el);
    const c = getComputedStyle(el).color;
    el.remove();
    return c || fallback;
  } catch {
    return fallback;
  }
}
function readPalette() {
  return {
    accent: cssColor("--color-accent", "rgb(20,120,130)"),
    ink: cssColor("--color-ink", "rgb(40,40,40)"),
    faint: cssColor("--color-ink-faint", "rgb(150,150,150)"),
    link: cssColor("--color-border", "rgb(210,210,210)"),
    canvas: cssColor("--color-canvas", "rgb(255,255,255)"),
  };
}

interface FNode { id: string; etype: string; deg: number; x?: number; y?: number }

export function KbGraph({ kbId, canEdit }: { kbId: string; canEdit: boolean }) {
  const { t } = useTranslation();
  const wrapRef = useRef<HTMLDivElement>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const fgRef = useRef<any>(null);
  const fitted = useRef(false);
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const [building, setBuilding] = useState(false);
  const [progress, setProgress] = useState(0);
  const pollRef = useRef<number | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [width, setWidth] = useState(640);
  const [hover, setHover] = useState<string | null>(null);
  const [palette, setPalette] = useState(readPalette);
  const [nodeQuery, setNodeQuery] = useState("");
  const [searchMiss, setSearchMiss] = useState(false);

  const load = useCallback(async () => {
    try { const d = await getGraph(kbId); setNodes(d.nodes); setEdges(d.edges); fitted.current = false; }
    finally { setLoaded(true); }
  }, [kbId]);
  useEffect(() => { void load(); }, [load]);

  // Adapt to container width
  useEffect(() => {
    if (!wrapRef.current) return;
    const ro = new ResizeObserver((es) => { for (const e of es) setWidth(e.contentRect.width); });
    ro.observe(wrapRef.current);
    return () => ro.disconnect();
  }, []);

  // Re-read the palette on theme change
  useEffect(() => {
    const mo = new MutationObserver(() => setPalette(readPalette()));
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["class", "data-theme", "style"] });
    return () => mo.disconnect();
  }, []);

  const stopPoll = useCallback(() => { if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; } }, []);
  const startPoll = useCallback(() => {
    if (pollRef.current) return;
    pollRef.current = window.setInterval(async () => {
      try {
        const s = await graphStatus(kbId);
        setProgress(s.progress);
        if (s.status !== "running") { stopPoll(); setBuilding(false); await load(); }
      } catch { /* ignore */ }
    }, 2000);
  }, [kbId, load, stopPoll]);

  // On enter/refresh: if a build is already running, resume the progress bar
  useEffect(() => {
    graphStatus(kbId).then((s) => { if (s.status === "running") { setBuilding(true); setProgress(s.progress); startPoll(); } }).catch(() => {});
    return () => stopPoll();
  }, [kbId, startPoll, stopPoll]);

  async function build() {
    setBuilding(true); setProgress(0);
    try {
      const r = await buildGraph(kbId);
      if (r.status === "running") startPoll();
      else { setBuilding(false); await load(); }   // returns immediately when there are no sources, etc.
    } catch { setBuilding(false); }
  }

  // Adjacency map (for hover highlighting)
  const adj = useMemo(() => {
    const m: Record<string, Set<string>> = {};
    edges.forEach((e) => { (m[e.source] ??= new Set()).add(e.target); (m[e.target] ??= new Set()).add(e.source); });
    return m;
  }, [edges]);

  // force-graph data (name as id; degree determines size; backfill edge endpoints)
  const data = useMemo(() => {
    const deg: Record<string, number> = {};
    edges.forEach((e) => { deg[e.source] = (deg[e.source] ?? 0) + 1; deg[e.target] = (deg[e.target] ?? 0) + 1; });
    const seen = new Set<string>();
    const fnodes: FNode[] = [];
    const push = (id: string, etype: string) => { if (id && !seen.has(id)) { seen.add(id); fnodes.push({ id, etype, deg: deg[id] ?? 0 }); } };
    nodes.forEach((n) => push(n.name, n.etype));
    edges.forEach((e) => { push(e.source, ""); push(e.target, ""); });
    return { nodes: fnodes, links: edges.map((e) => ({ source: e.source, target: e.target, type: e.type })) };
  }, [nodes, edges]);

  const dim = (id: string) => hover !== null && hover !== id && !adj[hover]?.has(id);

  function focusNode(name: string) {
    const q = name.trim().toLowerCase();
    if (!q) return;
    const node = data.nodes.find((n) => n.id.toLowerCase() === q) ?? data.nodes.find((n) => n.id.toLowerCase().includes(q));
    if (!node) { setSearchMiss(true); return; }
    setSearchMiss(false);
    setHover(node.id);
    fgRef.current?.centerAt(node.x, node.y, 500);
    fgRef.current?.zoom(3, 500);
  }

  return (
    <div className="rounded-xl border border-border/70 bg-surface/40 p-4">
      <div className="mb-3 flex items-center justify-between">
        <span className="text-sm font-medium text-ink">
          {t("kb.graphTitle")} <span className="text-ink-faint">({data.nodes.length} · {data.links.length})</span>
        </span>
        <div className="flex items-center gap-1.5">
          {data.nodes.length > 0 && (
            <form onSubmit={(e) => { e.preventDefault(); focusNode(nodeQuery); }} className="relative hidden sm:block">
              <MagnifyingGlass className="absolute start-2.5 top-1/2 size-3.5 -translate-y-1/2 text-ink-faint" />
              <input value={nodeQuery} onChange={(e) => { setNodeQuery(e.target.value); setSearchMiss(false); }} placeholder={t("kb.graphSearchNode")}
                className={`w-40 rounded-full border bg-canvas py-1.5 ps-8 pe-2 text-xs text-ink outline-none transition focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/30 ${searchMiss ? "border-danger" : "border-border"}`} />
            </form>
          )}
          {data.nodes.length > 0 && (
            <button onClick={() => fgRef.current?.zoomToFit(400, 40)} title={t("kb.graphFit")}
              className="flex items-center gap-1 rounded-full border border-border px-2.5 py-1.5 text-xs text-ink-secondary transition hover:bg-canvas hover:text-ink">
              <ArrowsOut className="size-3.5" />
            </button>
          )}
          {canEdit && (
            <button onClick={build} disabled={building} className="flex items-center gap-1.5 rounded-full bg-accent px-3 py-1.5 text-xs font-medium text-white transition hover:bg-accent-hover disabled:opacity-60">
              <Sparkle className={`size-3.5 ${building ? "animate-pulse" : ""}`} /> {building ? `${t("kb.graphBuilding")} ${progress}%` : t("kb.graphBuild")}
            </button>
          )}
        </div>
      </div>

      {building && (
        <div className="mb-3 h-1.5 w-full overflow-hidden rounded-full bg-canvas">
          <div className="h-full rounded-full bg-accent transition-all duration-500" style={{ width: `${Math.max(5, progress)}%` }} />
        </div>
      )}

      <div ref={wrapRef} className="overflow-hidden rounded-lg" style={{ height: HEIGHT }}>
        {data.nodes.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center text-center">
            <GraphIcon className="size-10 text-ink-faint" />
            <p className="mt-3 text-sm text-ink-secondary">{loaded ? t("kb.graphEmpty") : t("common.loading")}</p>
          </div>
        ) : (
          <ForceGraph2D
            ref={fgRef}
            width={width}
            height={HEIGHT}
            graphData={data}
            backgroundColor="rgba(0,0,0,0)"
            cooldownTicks={120}
            d3VelocityDecay={0.3}
            nodeRelSize={5}
            nodeLabel={(n: object) => (n as FNode).id}
            linkLabel={(l: object) => (l as { type: string }).type}
            linkColor={() => palette.link}
            linkWidth={(l: object) => {
              const s = (l as { source: { id?: string } | string }).source;
              const tg = (l as { target: { id?: string } | string }).target;
              const sid = typeof s === "object" ? s.id : s, tid = typeof tg === "object" ? tg.id : tg;
              return hover && (sid === hover || tid === hover) ? 2 : 1;
            }}
            onNodeHover={(n: object | null) => { setHover(n ? (n as FNode).id : null); if (wrapRef.current) wrapRef.current.style.cursor = n ? "pointer" : "default"; }}
            onNodeClick={(n: object) => { const node = n as FNode; fgRef.current?.centerAt(node.x, node.y, 500); fgRef.current?.zoom(2.5, 500); }}
            onEngineStop={() => { if (!fitted.current) { fitted.current = true; fgRef.current?.zoomToFit(400, 40); } }}
            nodePointerAreaPaint={(n: object, color: string, ctx: CanvasRenderingContext2D) => {
              const node = n as FNode; const r = 4 + Math.min(8, node.deg * 1.3);
              ctx.fillStyle = color; ctx.beginPath(); ctx.arc(node.x ?? 0, node.y ?? 0, r + 2, 0, 2 * Math.PI); ctx.fill();
            }}
            nodeCanvasObject={(n: object, ctx: CanvasRenderingContext2D, scale: number) => {
              const node = n as FNode;
              const r = 4 + Math.min(8, node.deg * 1.3);
              const faded = dim(node.id);
              ctx.globalAlpha = faded ? 0.18 : 1;
              ctx.beginPath(); ctx.arc(node.x ?? 0, node.y ?? 0, r, 0, 2 * Math.PI);
              ctx.fillStyle = palette.accent; ctx.fill();
              ctx.lineWidth = 1.5 / scale; ctx.strokeStyle = palette.canvas; ctx.stroke();
              if (scale > 1.1 || hover === node.id || (hover && adj[hover]?.has(node.id))) {
                const fontSize = 11 / scale;
                ctx.font = `${fontSize}px -apple-system, system-ui, sans-serif`;
                ctx.textAlign = "center"; ctx.textBaseline = "top";
                ctx.fillStyle = hover === node.id ? palette.accent : palette.ink;
                ctx.fillText(node.id, node.x ?? 0, (node.y ?? 0) + r + 2 / scale);
              }
              ctx.globalAlpha = 1;
            }}
          />
        )}
      </div>
      {data.nodes.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
          <p className="text-[11px] text-ink-faint">{t("kb.graphHint")}</p>
          <span className="flex items-center gap-1.5 text-[11px] text-ink-faint">
            <span className="inline-block size-2.5 rounded-full" style={{ background: palette.accent }} /> {t("kb.graphLegend")}
            {searchMiss && <span className="ms-2 text-danger">{t("kb.graphNoNode")}</span>}
          </span>
        </div>
      )}
    </div>
  );
}
