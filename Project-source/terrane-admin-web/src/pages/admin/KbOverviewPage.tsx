/** Admin "Library overview" —— a platform-wide view of every workspace's knowledge bases (read-only metadata). */

import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Select } from "@/components/Select";
import { useKbOverview } from "@/lib/kbOverview";
import { StatusBadge } from "@/pages/admin/WorkspacesPage";

export function KbOverviewPage() {
  const { t } = useTranslation();
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [vis, setVis] = useState("");
  const query = useKbOverview({ page, q, visibility: vis });
  const data = query.data;
  const rows = data?.items ?? [];
  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;
  const cell = "px-3.5 py-2 text-[13px]";

  return (
    <div className="mx-auto max-w-5xl">
      <h1 className="text-xl font-semibold tracking-tight text-ink">{t("kbOverview.title")}</h1>
      <p className="mt-1 text-[13px] text-ink-secondary">{t("kbOverview.desc")}</p>

      <div className="mt-5 flex items-center gap-2">
        <input value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} placeholder={t("kbOverview.searchPlaceholder")}
          className="w-64 rounded-(--radius-control) border border-border bg-canvas px-3 py-1.5 text-sm text-ink outline-none focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/30" />
        <Select value={vis} onChange={(v) => { setVis(v); setPage(1); }}
          options={[{ value: "", label: t("kbOverview.allVis") },
            { value: "private", label: t("kbOverview.vis.private") },
            { value: "shared", label: t("kbOverview.vis.shared") },
            { value: "workspace", label: t("kbOverview.vis.workspace") }]} />
      </div>

      <div className="mt-4 overflow-hidden rounded-xl border border-border/70 bg-surface/40">
        <table className="w-full">
          <thead>
            <tr className="border-b border-border/60 text-[11px] uppercase tracking-wide text-ink-faint">
              <th className={`${cell} text-start font-medium`}>{t("kbOverview.col.name")}</th>
              <th className={`${cell} text-start font-medium`}>{t("kbOverview.col.workspace")}</th>
              <th className={`${cell} text-start font-medium`}>{t("kbOverview.col.visibility")}</th>
              <th className={`${cell} text-start font-medium`}>{t("kbOverview.col.sources")}</th>
              <th className={`${cell} text-start font-medium`}>{t("kbOverview.col.status")}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/50">
            {rows.map((kb) => (
              <tr key={kb.id} className="transition-colors hover:bg-surface">
                <td className={`${cell} text-ink`}>{kb.name}</td>
                <td className={`${cell} text-ink-secondary`}>{kb.workspace_name}</td>
                <td className={`${cell} text-ink-secondary`}>{t(`kbOverview.vis.${kb.visibility}`)}</td>
                <td className={`${cell} text-ink-secondary`}>{kb.source_count}</td>
                <td className={cell}><StatusBadge status={kb.status === "active" ? "active" : "suspended"} label={kb.status} /></td>
              </tr>
            ))}
            {!query.isLoading && rows.length === 0 && (
              <tr><td colSpan={5} className="px-3.5 py-12 text-center text-[13px] text-ink-faint">{t("kbOverview.empty")}</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {data && data.total > 0 && (
        <div className="mt-3 flex items-center justify-between text-[13px] text-ink-secondary">
          <span>{t("kbOverview.found", { n: data.total })}</span>
          <span className="flex items-center gap-2">
            <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="rounded px-2 py-1 hover:bg-canvas disabled:opacity-40">‹</button>
            {t("kbOverview.pageOf", { x: page, y: totalPages })}
            <button disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)} className="rounded px-2 py-1 hover:bg-canvas disabled:opacity-40">›</button>
          </span>
        </div>
      )}
    </div>
  );
}
