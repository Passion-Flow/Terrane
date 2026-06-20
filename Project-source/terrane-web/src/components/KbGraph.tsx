/** 知识图谱可视化(轻量 SVG 环形布局,无重依赖)。owner/editor 可「构建图谱」。 */

import { Graph, Sparkle } from "@phosphor-icons/react";
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { buildGraph, getGraph, type GraphEdge, type GraphNode } from "@/lib/kb";

const W = 640, H = 460;

export function KbGraph({ kbId, canEdit }: { kbId: string; canEdit: boolean }) {
  const { t } = useTranslation();
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(async () => {
    try { const d = await getGraph(kbId); setNodes(d.nodes); setEdges(d.edges); }
    finally { setLoaded(true); }
  }, [kbId]);
  useEffect(() => { void load(); }, [load]);

  async function build() {
    setBusy(true);
    try { await buildGraph(kbId); await load(); } finally { setBusy(false); }
  }

  const cx = W / 2, cy = H / 2, R = Math.min(W, H) * 0.38;
  const pos = new Map<string, { x: number; y: number }>();
  nodes.forEach((n, i) => {
    const a = (2 * Math.PI * i) / Math.max(nodes.length, 1) - Math.PI / 2;
    pos.set(n.name, { x: cx + R * Math.cos(a), y: cy + R * Math.sin(a) });
  });

  return (
    <div className="rounded-xl border border-border/70 bg-surface/40 p-4">
      <div className="mb-3 flex items-center justify-between">
        <span className="text-sm font-medium text-ink">{t("kb.graphTitle")} <span className="text-ink-faint">({nodes.length} · {edges.length})</span></span>
        {canEdit && (
          <button onClick={build} disabled={busy} className="flex items-center gap-1.5 rounded-full bg-accent px-3 py-1.5 text-xs font-medium text-white hover:bg-accent-hover disabled:opacity-50">
            <Sparkle className="size-3.5" /> {busy ? t("kb.graphBuilding") : t("kb.graphBuild")}
          </button>
        )}
      </div>
      {nodes.length === 0 ? (
        <div className="flex h-[420px] flex-col items-center justify-center text-center">
          <Graph className="size-10 text-ink-faint" />
          <p className="mt-3 text-sm text-ink-secondary">{loaded ? t("kb.graphEmpty") : t("common.loading")}</p>
        </div>
      ) : (
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ maxHeight: "60vh" }}>
          {edges.map((e, i) => {
            const a = pos.get(e.source), b = pos.get(e.target);
            if (!a || !b) return null;
            return (
              <g key={i}>
                <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="currentColor" className="text-border" strokeWidth={1} />
                <text x={(a.x + b.x) / 2} y={(a.y + b.y) / 2} className="fill-ink-faint" fontSize={9} textAnchor="middle">{e.type}</text>
              </g>
            );
          })}
          {nodes.map((n) => {
            const p = pos.get(n.name);
            if (!p) return null;
            return (
              <g key={n.id}>
                <circle cx={p.x} cy={p.y} r={5} className="fill-accent" />
                <text x={p.x} y={p.y - 9} className="fill-ink" fontSize={11} textAnchor="middle">{n.name}</text>
              </g>
            );
          })}
        </svg>
      )}
    </div>
  );
}
