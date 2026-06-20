/** 设置 → 邮件服务（SMTP）。向导后随时编辑；密码脱敏（留空不变）。字段标签复用 wizard.*。 */

import { PaperPlaneTilt } from "@phosphor-icons/react";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { useAuth } from "@/auth/AuthContext";
import { Select } from "@/components/Select";
import { testEmail, updateEmail, useSettings } from "@/lib/settings";
import type { Encryption } from "@/lib/wizard";
import { field, SettingsShell, Toast, toErrText, type ToastMsg } from "@/pages/admin/settings/_shared";

export function EmailSettingsPage() {
  const { t } = useTranslation();
  const { has } = useAuth();
  const qc = useQueryClient();
  const query = useSettings();
  const canWrite = has("system.settings.write");
  const ro = !canWrite;

  const [toast, setToast] = useState<ToastMsg | null>(null);
  const [busy, setBusy] = useState(false);

  const [presetId, setPresetId] = useState("");
  const [host, setHost] = useState("");
  const [port, setPort] = useState(465);
  const [encryption, setEncryption] = useState<Encryption>("auto");
  const [smtpUser, setSmtpUser] = useState("");
  const [smtpPass, setSmtpPass] = useState("");
  const [fromAddr, setFromAddr] = useState("");
  const [fromName, setFromName] = useState("Terrane");
  const [allowInsecure, setAllowInsecure] = useState(false);
  const [hasPassword, setHasPassword] = useState(false);

  const [hydrated, setHydrated] = useState(false);
  useEffect(() => {
    const s = query.data;
    if (!s || hydrated) return;
    // 按已保存的 host 反推邮箱服务商预设（后端不存 preset id）→ 下拉回显。
    const matched = s.email.host
      ? s.email_presets.find((p) => p.host && p.host === s.email.host)
      : undefined;
    setPresetId(matched?.id ?? "");
    setHost(s.email.host || "");
    setPort(s.email.port || 465);
    setEncryption(s.email.encryption || "auto");
    setSmtpUser(s.email.username || "");
    setFromAddr(s.email.from_address || "");
    setFromName(s.email.from_name || "Terrane");
    setAllowInsecure(!!s.email.allow_insecure);
    setHasPassword(!!s.email.has_password);
    setHydrated(true);
  }, [query.data, hydrated]);

  const payload = () => ({
    host, port, encryption, username: smtpUser, password: smtpPass,
    from_address: fromAddr, from_name: fromName || "Terrane", allow_insecure: allowInsecure,
  });

  function applyPreset(id: string) {
    setPresetId(id);
    const p = query.data?.email_presets.find((x) => x.id === id);
    if (!p) return;
    if (p.host) setHost(p.host);
    setPort(p.port);
    setEncryption(p.encryption as Encryption);
  }
  const selectedPreset = query.data?.email_presets.find((x) => x.id === presetId);

  async function onSave() {
    setBusy(true);
    try {
      await updateEmail(payload());
      await qc.invalidateQueries({ queryKey: ["settings"] });
      if (smtpPass) setHasPassword(true);
      setSmtpPass("");
      setToast({ kind: "success", text: t("settings.savedEmail") });
    } catch (e) { setToast({ kind: "error", text: toErrText(e, t) }); }
    finally { setBusy(false); }
  }

  async function onTest() {
    setBusy(true);
    try {
      await updateEmail(payload());  // 先保存当前配置再测连
      await qc.invalidateQueries({ queryKey: ["settings"] });
      if (smtpPass) setHasPassword(true);
      setSmtpPass("");
      await testEmail(fromAddr || smtpUser);
      setToast({ kind: "success", text: t("settings.testSent") });
    } catch (e) { setToast({ kind: "error", text: toErrText(e, t) }); }
    finally { setBusy(false); }
  }

  return (
    <SettingsShell title={t("settings.email.title")} desc={t("settings.email.desc")}>
      <div className="space-y-4">
        <label className="block text-sm font-medium text-ink">{t("wizard.provider")}
          <Select className="mt-1.5" value={presetId} onChange={applyPreset}
            placeholder={t("wizard.providerPick")} disabled={ro || busy}
            ariaLabel={t("wizard.provider")}
            options={(query.data?.email_presets ?? []).map((p) => ({ value: p.id, label: p.label }))} />
        </label>
        {selectedPreset?.password_hint && (
          <p className="rounded-(--radius-control) bg-accent-soft px-3 py-2 text-xs text-accent">
            {selectedPreset.password_hint}</p>
        )}

        <div className="grid grid-cols-2 gap-3">
          <label className="col-span-2 text-sm font-medium text-ink">{t("wizard.smtpHost")}
            <input value={host} onChange={(e) => setHost(e.target.value)} placeholder="smtp.example.com"
              disabled={ro || busy} className={`mt-1.5 ${field}`} /></label>
          <label className="text-sm font-medium text-ink">{t("wizard.smtpPort")}
            <input type="number" value={port} onChange={(e) => setPort(Number(e.target.value))}
              disabled={ro || busy} className={`mt-1.5 ${field}`} /></label>
          <label className="text-sm font-medium text-ink">{t("wizard.smtpEncryption")}
            <Select className="mt-1.5" value={encryption} onChange={(v) => setEncryption(v as Encryption)}
              disabled={ro || busy} ariaLabel={t("wizard.smtpEncryption")}
              options={[
                { value: "auto", label: t("wizard.encAuto") },
                { value: "ssl", label: t("wizard.encSsl") },
                { value: "starttls", label: t("wizard.encStarttls") },
                { value: "none", label: t("wizard.encNone") },
              ]} /></label>
          <label className="text-sm font-medium text-ink">{t("wizard.smtpUser")}
            <input value={smtpUser} onChange={(e) => setSmtpUser(e.target.value)} autoComplete="off"
              disabled={ro || busy} className={`mt-1.5 ${field}`} /></label>
          <label className="text-sm font-medium text-ink">{t("wizard.smtpPass")}
            <input type="password" value={smtpPass} onChange={(e) => setSmtpPass(e.target.value)}
              autoComplete="new-password" disabled={ro || busy}
              placeholder={hasPassword ? "••••••••••" : ""}
              className={`mt-1.5 ${field}`} />
            {hasPassword && (
              <span className="mt-1 block text-xs text-ink-faint">{t("settings.passwordKept")}</span>
            )}</label>
          <label className="text-sm font-medium text-ink">{t("wizard.smtpFromName")}
            <input value={fromName} onChange={(e) => setFromName(e.target.value)} placeholder="Terrane"
              disabled={ro || busy} className={`mt-1.5 ${field}`} /></label>
          <label className="text-sm font-medium text-ink">{t("wizard.smtpFrom")}
            <input value={fromAddr} onChange={(e) => setFromAddr(e.target.value)}
              placeholder="no-reply@example.com" disabled={ro || busy} className={`mt-1.5 ${field}`} />
            {selectedPreset?.from_locked && (
              <span className="mt-1 block text-xs text-ink-faint">{t("wizard.fromLockedHint")}</span>
            )}</label>
          <label className="col-span-2 flex items-center gap-2 pt-1 text-sm text-ink-secondary">
            <input type="checkbox" checked={allowInsecure}
              onChange={(e) => setAllowInsecure(e.target.checked)} disabled={ro || busy}
              className="size-4 accent-[var(--color-accent,#0f9b8e)]" />
            {t("wizard.allowInsecure")}</label>
        </div>

        {canWrite && (
          <div className="flex items-center gap-3 pt-1">
            <button type="button" onClick={onTest} disabled={busy || !host || !fromAddr}
              className="flex items-center gap-1.5 rounded-(--radius-control) border border-border px-3.5 py-2 text-sm text-ink-secondary hover:bg-canvas hover:text-ink disabled:opacity-50">
              <PaperPlaneTilt className="size-4" /> {t("settings.test")}</button>
            <span className="flex-1" />
            <button type="button" onClick={onSave} disabled={busy || !host || !fromAddr}
              className="rounded-(--radius-control) bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-50">
              {busy ? t("common.saving") : t("common.save")}</button>
          </div>
        )}
      </div>
      <Toast toast={toast} onDone={() => setToast(null)} />
    </SettingsShell>
  );
}
