/** Audit log viewer —— read-only, page-based pagination. Filterable by action (trailing dot = prefix match). Compact, refined table. */

import { MagnifyingGlass } from "@phosphor-icons/react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Pagination } from "@/components/Pagination";
import { AUDIT_PAGE_SIZE, useAuditLogs, type AuditLogItem } from "@/lib/auditLogs";

function fmtTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, { month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function AuditLogsPage() {
  const { t } = useTranslation();
  const [actionInput, setActionInput] = useState("");
  const [filters, setFilters] = useState<{ action?: string }>({});
  const [page, setPage] = useState(1);

  const q = useAuditLogs(filters, page);
  const rows: AuditLogItem[] = q.data?.items ?? [];
  const total = q.data?.total ?? 0;

  function applyFilter(e: React.FormEvent) {
    e.preventDefault();
    setPage(1);
    setFilters(actionInput.trim() ? { action: actionInput.trim() } : {});
  }

  const actionLabel = (a: string) => t(`audit.action.${a.replaceAll(".", "_")}`, { defaultValue: a });
  const actorTypeLabel = (k: string) => t(`audit.actorType.${k}`, { defaultValue: k });
  function renderTarget(r: AuditLogItem): string {
    if (!r.target_type) return "—";
    const typeLabel = t(`audit.targetType.${r.target_type}`, { defaultValue: r.target_type });
    // Prefer the human-readable name snapshotted at write time (email / workspace name); next the setting key dictionary; otherwise fall back to a short id code.
    if (r.target_name) return `${typeLabel} · ${r.target_name}`;
    if (!r.target_id || r.target_id === "singleton") return typeLabel;
    const known = t(`audit.targetId.${r.target_id}`, { defaultValue: "" });
    if (known) return `${typeLabel} · ${known}`;
    return `${typeLabel} · ${r.target_id.slice(0, 8)}`;
  }

  const cell = "px-3.5 py-2 text-[13px]";

  return (
    <div className="mx-auto max-w-5xl">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-ink">{t("audit.title")}</h1>
          <p className="mt-1 text-[13px] text-ink-secondary">{t("audit.desc")}</p>
        </div>
      </div>

      <form onSubmit={applyFilter} className="mt-5 flex items-center gap-2">
        <div className="relative w-full max-w-xs">
          <MagnifyingGlass className="absolute inset-y-0 start-3 my-auto size-4 text-ink-faint" />
          <input value={actionInput} onChange={(e) => setActionInput(e.target.value)}
            placeholder={t("audit.actionPlaceholder")}
            className="w-full rounded-full border border-border bg-canvas py-1.5 ps-9 pe-3 text-[13px] text-ink outline-none transition focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/30" />
        </div>
        <button type="submit"
          className="rounded-full bg-accent px-3.5 py-1.5 text-[13px] font-medium text-white transition hover:bg-accent-hover">
          {t("audit.filter")}
        </button>
      </form>

      <div className="mt-4 overflow-hidden rounded-xl border border-border/70 bg-surface/40">
        <table className="w-full">
          <thead>
            <tr className="border-b border-border/60 text-[11px] uppercase tracking-wide text-ink-faint">
              <th className={`${cell} text-start font-medium`}>{t("audit.col.time")}</th>
              <th className={`${cell} text-start font-medium`}>{t("audit.col.actor")}</th>
              <th className={`${cell} text-start font-medium`}>{t("audit.col.action")}</th>
              <th className={`${cell} text-start font-medium`}>{t("audit.col.target")}</th>
              <th className={`${cell} text-start font-medium`}>{t("audit.col.ip")}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/50">
            {rows.map((r) => (
              <tr key={r.id} className="transition-colors hover:bg-surface">
                <td className={`${cell} whitespace-nowrap text-ink-secondary tabular-nums`}>{fmtTime(r.created_at)}</td>
                <td className={cell}>
                  <span className="text-ink">{r.actor_name ?? r.actor_id?.slice(0, 8) ?? "—"}</span>
                  <span className="ms-1.5 rounded bg-canvas px-1 py-px text-[10px] text-ink-faint">
                    {actorTypeLabel(r.actor_type)}
                  </span>
                </td>
                <td className={`${cell} text-ink`}>{actionLabel(r.action)}</td>
                <td className={`${cell} text-ink-secondary`}>{renderTarget(r)}</td>
                <td className={`${cell} whitespace-nowrap font-mono text-xs text-ink-faint`}>{r.ip ?? "—"}</td>
              </tr>
            ))}
            {!q.isLoading && rows.length === 0 && (
              <tr><td colSpan={5} className="px-3.5 py-12 text-center text-[13px] text-ink-faint">{t("audit.empty")}</td></tr>
            )}
            {q.isLoading && rows.length === 0 && (
              <tr><td colSpan={5} className="px-3.5 py-12 text-center text-[13px] text-ink-faint">{t("common.loading")}</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <Pagination page={page} total={total} pageSize={AUDIT_PAGE_SIZE} onPage={setPage} />
    </div>
  );
}
