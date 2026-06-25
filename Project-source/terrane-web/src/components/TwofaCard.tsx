/** Account page 2FA (TOTP) card — enable (secret + code → backup codes) / disable. */

import { CheckCircle, ShieldCheck } from "@phosphor-icons/react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { useAuth } from "@/auth/AuthContext";
import { twofaBegin, twofaDisable, twofaEnable } from "@/lib/twofa";

export function TwofaCard() {
  const { t } = useTranslation();
  const { user, refresh } = useAuth();
  const enabled = !!user?.twofa_enabled;

  const [mode, setMode] = useState<"idle" | "enroll" | "backups">("idle");
  const [secret, setSecret] = useState("");
  const [code, setCode] = useState("");
  const [backups, setBackups] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function begin() {
    setBusy(true); setErr("");
    try { const r = await twofaBegin(); setSecret(r.data.secret); setMode("enroll"); setCode(""); }
    catch { setErr(t("twofa.error")); } finally { setBusy(false); }
  }
  async function enable() {
    if (!code.trim() || busy) return;
    setBusy(true); setErr("");
    try { const r = await twofaEnable(code.trim()); setBackups(r.data.backup_codes); setMode("backups"); await refresh(); }
    catch { setErr(t("twofa.codeInvalid")); } finally { setBusy(false); }
  }
  async function disable() {
    if (!code.trim() || busy) return;
    setBusy(true); setErr("");
    try { await twofaDisable(code.trim()); setMode("idle"); setCode(""); await refresh(); }
    catch { setErr(t("twofa.codeInvalid")); } finally { setBusy(false); }
  }

  const field = "rounded-(--radius-control) border border-border bg-canvas px-3 py-2 text-sm text-ink outline-none focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/30";

  return (
    <div className="mt-5 rounded-xl border border-border/70 bg-surface/40 p-5">
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-2 text-sm text-ink">
          <ShieldCheck className="size-4.5 text-ink-faint" /> {t("twofa.title")}
          {enabled && <span className="flex items-center gap-1 rounded bg-accent-soft px-1.5 py-0.5 text-[11px] text-accent"><CheckCircle className="size-3" weight="fill" /> {t("twofa.on")}</span>}
        </span>
        {mode === "idle" && (enabled
          ? <button onClick={() => setMode("enroll")} className="rounded-(--radius-control) border border-border px-3 py-1.5 text-[13px] text-danger hover:bg-danger-soft">{t("twofa.disable")}</button>
          : <button onClick={begin} disabled={busy} className="rounded-(--radius-control) bg-accent px-3 py-1.5 text-[13px] font-medium text-white hover:bg-accent-hover disabled:opacity-50">{t("twofa.enable")}</button>)}
      </div>

      {mode === "enroll" && !enabled && (
        <div className="mt-4 space-y-3">
          <p className="text-[13px] text-ink-secondary">{t("twofa.enrollHint")}</p>
          <code className="block break-all rounded bg-canvas px-3 py-2 text-xs text-ink">{secret}</code>
          <div className="flex items-center gap-2">
            <input value={code} onChange={(e) => setCode(e.target.value)} placeholder={t("twofa.codePlaceholder")} inputMode="numeric" className={`${field} w-40`} />
            <button onClick={enable} disabled={busy || !code.trim()} className="rounded-(--radius-control) bg-accent px-3.5 py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-50">{t("twofa.confirm")}</button>
            <button onClick={() => setMode("idle")} className="text-[13px] text-ink-secondary hover:text-ink">{t("common.cancel")}</button>
          </div>
        </div>
      )}

      {mode === "enroll" && enabled && (
        <div className="mt-4 flex items-center gap-2">
          <input value={code} onChange={(e) => setCode(e.target.value)} placeholder={t("twofa.codeOrBackup")} className={`${field} w-48`} />
          <button onClick={disable} disabled={busy || !code.trim()} className="rounded-(--radius-control) bg-danger px-3.5 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50">{t("twofa.confirmDisable")}</button>
          <button onClick={() => setMode("idle")} className="text-[13px] text-ink-secondary hover:text-ink">{t("common.cancel")}</button>
        </div>
      )}

      {mode === "backups" && (
        <div className="mt-4 space-y-2">
          <p className="text-[13px] font-medium text-danger">{t("twofa.backupHint")}</p>
          <div className="grid grid-cols-2 gap-1.5 rounded-(--radius-control) bg-canvas p-3 font-mono text-xs text-ink sm:grid-cols-5">
            {backups.map((b) => <span key={b}>{b}</span>)}
          </div>
          <button onClick={() => setMode("idle")} className="text-[13px] text-accent hover:underline">{t("twofa.done")}</button>
        </div>
      )}

      {err && <p className="mt-2 text-[13px] text-danger">{err}</p>}
    </div>
  );
}
