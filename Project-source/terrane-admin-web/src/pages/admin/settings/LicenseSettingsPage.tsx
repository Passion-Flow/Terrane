/** 设置 → License。授权详情(许可证状态 + 订阅配额) + 激活/换证(超管,已激活态须鉴权)。
 *  对齐 Relio/Dify:两张卡片 + 右上「激活」→ 居中模态(在线/离线 + 凭据)。 */

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { useAuth } from "@/auth/AuthContext";
import { Modal } from "@/components/Modal";
import { ApiError } from "@/lib/api";
import { activateLicense, getLicenseCard } from "@/lib/license";
import { useWorkspaces } from "@/lib/workspaces";
import { StatusBadge } from "@/pages/admin/WorkspacesPage";

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "2-digit", day: "2-digit" });
}

function Row({ label, children, mono }: { label: string; children: React.ReactNode; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3 py-2.5">
      <dt className="shrink-0 text-[13px] text-ink-secondary">{label}</dt>
      <dd className={`min-w-0 truncate text-end text-[13px] text-ink ${mono ? "font-mono text-xs" : ""}`}>{children}</dd>
    </div>
  );
}

export function LicenseSettingsPage() {
  const { t } = useTranslation();
  const { has } = useAuth();
  const qc = useQueryClient();
  const { data: lic } = useQuery({ queryKey: ["license-card"], queryFn: getLicenseCard });
  const ws = useWorkspaces("", 1, 1);
  const canActivate = has("platform.license.update");

  const [open, setOpen] = useState(false);
  const [method, setMethod] = useState<"online" | "offline">("online");
  const [credential, setCredential] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const offline = method === "offline";

  const limit = (v: number | null | undefined) => (v == null ? t("settings.license.unlimited") : String(v));

  async function onActivate() {
    if (!credential.trim() || busy) return;
    setBusy(true); setErr("");
    try {
      await activateLicense(method, credential.trim());
      await qc.invalidateQueries({ queryKey: ["license-card"] });
      setOpen(false); setCredential("");
    } catch (e) {
      setErr(e instanceof ApiError ? t(`errors.${e.code}`) : t("errors.SYSTEM_HTTP_ERROR"));
    } finally { setBusy(false); }
  }

  return (
    <div className="mx-auto max-w-3xl">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-ink">{t("settings.license.title")}</h1>
          <p className="mt-1 text-[13px] text-ink-secondary">{t("settings.license.desc")}</p>
        </div>
        {canActivate && (
          <button type="button" onClick={() => { setMethod("online"); setCredential(""); setErr(""); setOpen(true); }}
            className="shrink-0 rounded-full bg-accent px-4 py-1.5 text-[13px] font-medium text-white transition hover:bg-accent-hover">
            {t("activate.openButton")}
          </button>
        )}
      </div>

      {/* 许可证状态 */}
      <section className="mt-5 rounded-xl border border-border/70 bg-surface/40 p-5">
        <h2 className="border-b border-border/60 pb-3 text-base font-semibold text-ink">{t("settings.license.current")}</h2>
        <dl className="mt-1 divide-y divide-border/50">
          <Row label={t("settings.license.statusLabel")}>
            {lic && <StatusBadge status={lic.status} label={t(`license.status.${lic.status}`, { defaultValue: lic.status })} />}
          </Row>
          <Row label={t("settings.license.activeFrom")}>{fmtDate(lic?.active_from)}</Row>
          <Row label={t("overview.activeUntil")}>
            {fmtDate(lic?.active_until)}
            {lic?.days_left != null && <span className="ms-2 text-ink-faint">{t("overview.days", { n: lic.days_left })}</span>}
          </Row>
          <Row label={t("overview.licenseId")} mono>{lic?.license_id_masked ?? "—"}</Row>
          <Row label={t("settings.license.deploymentId")} mono>{lic?.fingerprint ?? "—"}</Row>
        </dl>
      </section>

      {/* 订阅 */}
      <section className="mt-5 rounded-xl border border-border/70 bg-surface/40 p-5">
        <h2 className="border-b border-border/60 pb-3 text-base font-semibold text-ink">{t("overview.subscription")}</h2>
        <dl className="mt-1 divide-y divide-border/50">
          <Row label={t("settings.license.workspaces")}>
            <span className="tabular-nums">{ws.data?.total ?? "—"}</span>
            <span className="text-ink-faint"> / {limit(lic?.quotas?.workspaces)}</span>
          </Row>
          <Row label={t("settings.license.membersLimit")}>{limit(lic?.quotas?.members)}</Row>
        </dl>
      </section>

      {/* 激活/换证模态 */}
      <Modal open={open} onClose={() => setOpen(false)} title={t("activate.modalTitle")}
        footer={<>
          <button type="button" onClick={() => setOpen(false)} className="rounded-(--radius-control) px-3.5 py-1.5 text-[13px] text-ink-secondary hover:bg-canvas">{t("activate.cancel")}</button>
          <button type="button" onClick={onActivate} disabled={busy || !credential.trim()}
            className="rounded-(--radius-control) bg-accent px-3.5 py-1.5 text-[13px] font-medium text-white hover:bg-accent-hover disabled:opacity-50">
            {busy ? t("activate.submitting") : t("activate.submit")}</button>
        </>}>
        <div className="space-y-3.5">
          <p className="text-[13px] text-ink-secondary">{t("activate.modalSubtitle")}</p>
          <div>
            <div className="mb-1.5 text-sm font-medium text-ink">{t("activate.method")}</div>
            <div className="flex gap-4">
              {(["online", "offline"] as const).map((m) => (
                <label key={m} className="flex items-center gap-2 text-sm text-ink-secondary">
                  <input type="radio" name="lic-method" checked={method === m} onChange={() => setMethod(m)}
                    disabled={busy} className="size-4 accent-[var(--color-accent,#0f9b8e)]" />
                  {t(`activate.${m}`)}
                </label>
              ))}
            </div>
          </div>
          <label className="block text-sm font-medium text-ink">
            {t(offline ? "activate.pasteLabel" : "activate.codeLabel")}
            {offline ? (
              <textarea value={credential} onChange={(e) => setCredential(e.target.value)} rows={5}
                placeholder={t("activate.pastePlaceholder")} disabled={busy}
                className="mt-1.5 w-full rounded-(--radius-control) border border-border bg-canvas px-3 py-2 font-mono text-xs text-ink outline-none focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/30" />
            ) : (
              <input value={credential} onChange={(e) => setCredential(e.target.value)}
                placeholder={t("activate.codePlaceholder")} disabled={busy} autoComplete="off"
                className="mt-1.5 w-full rounded-(--radius-control) border border-border bg-canvas px-3 py-2 text-sm text-ink outline-none focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/30" />
            )}
          </label>
          {err && <p className="text-[13px] text-danger">{err}</p>}
        </div>
      </Modal>
    </div>
  );
}
