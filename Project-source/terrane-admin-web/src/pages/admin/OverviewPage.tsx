/** 概览 —— 后台首页仪表盘:关键计数(工作区/成员/操作员) + License 摘要 + 近期审计。
 *  全只读;按权限渲染卡片(无权读的领域不显示)。数据复用各列表/License 端点。 */

import { Buildings, UserGear, UsersThree, type Icon } from "@phosphor-icons/react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router";

import { useAuth } from "@/auth/AuthContext";
import { FALLBACK_LANG, isSupported } from "@/i18n/langs";
import { useAuditLogs } from "@/lib/auditLogs";
import { getLicenseCard } from "@/lib/license";
import { useMembers } from "@/lib/members";
import { useOperators } from "@/lib/operators";
import { useWorkspaces } from "@/lib/workspaces";
import { StatusBadge } from "@/pages/admin/WorkspacesPage";

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "2-digit", day: "2-digit" });
}
function fmtTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function StatCard({ icon: Ico, label, value, to }: { icon: Icon; label: string; value: string; to: string }) {
  return (
    <Link to={to}
      className="flex items-center gap-4 rounded-xl border border-border/70 bg-surface/40 p-5 transition-colors hover:border-border hover:bg-surface">
      <span className="flex size-11 shrink-0 items-center justify-center rounded-(--radius-control) bg-accent-soft text-accent">
        <Ico className="size-5" />
      </span>
      <span className="min-w-0">
        <span className="block text-2xl font-bold tabular-nums tracking-tight text-ink">{value}</span>
        <span className="block truncate text-[13px] text-ink-secondary">{label}</span>
      </span>
    </Link>
  );
}

export function OverviewPage() {
  const { t } = useTranslation();
  const { has, user } = useAuth();
  const { lang } = useParams();
  const seg = lang && isSupported(lang) ? lang : FALLBACK_LANG;
  const base = `/${seg}/admin`;

  const canWs = has("platform.workspace.read");
  const canUser = has("platform.user.read");
  const canAudit = has("platform.audit.read");
  const canLicense = has("platform.license.read");

  const ws = useWorkspaces("", 1, 1);
  const mem = useMembers({}, 1, 1);
  const ops = useOperators({}, 1, 1);
  const lic = useQuery({ queryKey: ["license-card"], queryFn: getLicenseCard });
  const audit = useAuditLogs({}, 1, 6);

  const num = (n: number | undefined) => (n === undefined ? "—" : String(n));
  const actionLabel = (a: string) => t(`audit.action.${a.replaceAll(".", "_")}`, { defaultValue: a });

  return (
    <div className="mx-auto max-w-5xl">
      <h1 className="text-xl font-semibold tracking-tight text-ink">{t("admin.welcomeTitle")}</h1>
      <p className="mt-1 text-[13px] text-ink-secondary">
        {t("admin.welcomeDesc", { name: user?.username ?? user?.email ?? "" })}
      </p>

      {/* 计数卡 */}
      <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {canWs && <StatCard icon={Buildings} label={t("admin.nav.workspaces")} value={num(ws.data?.total)} to={`${base}/workspaces`} />}
        {canUser && <StatCard icon={UsersThree} label={t("admin.nav.members")} value={num(mem.data?.total)} to={`${base}/members`} />}
        {canUser && <StatCard icon={UserGear} label={t("operators.title")} value={num(ops.data?.total)} to={`${base}/settings/operators`} />}
      </div>

      <div className="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-2">
        {/* License 摘要 —— 开源版（门控关闭）隐藏整块 */}
        {canLicense && lic.data?.required !== false && (
          <section className="rounded-xl border border-border/70 bg-surface/40 p-5">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-semibold text-ink">{t("overview.license")}</h2>
              {lic.data && <StatusBadge status={lic.data.status} label={t(`license.status.${lic.data.status}`, { defaultValue: lic.data.status })} />}
            </div>
            <dl className="mt-4 space-y-2.5 text-[13px]">
              <Row label={t("overview.product")} value={lic.data?.product ?? "—"} />
              <Row label={t("overview.subscription")} value={lic.data?.subscription ?? "—"} />
              <Row label={t("overview.daysLeft")} value={lic.data?.days_left != null ? t("overview.days", { n: lic.data.days_left }) : "—"} />
              <Row label={t("overview.activeUntil")} value={fmtDate(lic.data?.active_until ?? null)} />
              <Row label={t("overview.licenseId")} value={lic.data?.license_id_masked ?? "—"} mono />
            </dl>
          </section>
        )}

        {/* 近期审计 */}
        {canAudit && (
          <section className="rounded-xl border border-border/70 bg-surface/40 p-5">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-semibold text-ink">{t("overview.recentAudit")}</h2>
              <Link to={`${base}/audit-logs`} className="text-[13px] text-accent hover:underline">{t("overview.viewAll")}</Link>
            </div>
            <ul className="mt-3 divide-y divide-border/50">
              {(audit.data?.items ?? []).map((r) => (
                <li key={r.id} className="flex items-center justify-between gap-3 py-2 text-[13px]">
                  <span className="min-w-0 truncate">
                    <span className="text-ink">{r.actor_name ?? r.actor_id?.slice(0, 8) ?? "—"}</span>
                    <span className="ms-1.5 text-ink-secondary">{actionLabel(r.action)}</span>
                  </span>
                  <span className="shrink-0 whitespace-nowrap tabular-nums text-ink-faint">{fmtTime(r.created_at)}</span>
                </li>
              ))}
              {!audit.isLoading && (audit.data?.items.length ?? 0) === 0 && (
                <li className="py-6 text-center text-[13px] text-ink-faint">{t("audit.empty")}</li>
              )}
            </ul>
          </section>
        )}
      </div>
    </div>
  );
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-ink-secondary">{label}</dt>
      <dd className={`truncate text-ink ${mono ? "font-mono text-xs" : ""}`}>{value}</dd>
    </div>
  );
}
