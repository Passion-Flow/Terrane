/** Setup wizard (PRD 4.12.1: License -> super admin -> email -> branding -> done).
 *  Forced after the super admin's first-login password change (RequireSetup hooks the wizard state).
 *  The license/super-admin steps are already done (read-only display); email/branding can be filled in or skipped;
 *  finishing marks it completed and navigates to /admin. Reachable by super admin only (backend PERM_DENIED as a fallback). */

import { CheckCircle, Circle, PaperPlaneTilt, XCircle } from "@phosphor-icons/react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router";

import { useAuth } from "@/auth/AuthContext";
import { LanguageSelect } from "@/components/LanguageSelect";
import { Logo } from "@/components/Logo";
import { Select } from "@/components/Select";
import { ThemeToggle } from "@/components/ThemeToggle";
import { FALLBACK_LANG, isSupported } from "@/i18n/langs";
import { ApiError } from "@/lib/api";
import { getLicenseCard } from "@/lib/license";
import {
  completeWizard,
  getWizard,
  saveBranding,
  saveEmail,
  testEmail,
  type Encryption,
} from "@/lib/wizard";

interface ToastMsg {
  kind: "error" | "success";
  text: string;
}

function Toast({ toast, onDone }: { toast: ToastMsg | null; onDone: () => void }) {
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(onDone, 4000);
    return () => clearTimeout(timer);
  }, [toast, onDone]);
  if (!toast) return null;
  const error = toast.kind === "error";
  return (
    <div
      role="alert"
      className={`fixed end-6 top-6 z-50 flex max-w-sm items-center gap-2 rounded-(--radius-control) px-4 py-3 text-sm shadow-lg ${
        error ? "bg-danger-soft text-danger" : "bg-accent-soft text-accent"
      }`}
    >
      {error ? <XCircle className="size-4 shrink-0" weight="fill" /> : <CheckCircle className="size-4 shrink-0" weight="fill" />}
      {toast.text}
    </div>
  );
}

const RAIL: Array<{ key: string }> = [
  { key: "license" }, { key: "super_admin" }, { key: "email" }, { key: "branding" }, { key: "done" },
];

const field =
  "w-full rounded-(--radius-control) border border-border bg-canvas px-3.5 py-2.5 text-sm text-ink outline-none transition placeholder:text-ink-faint focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/40 disabled:opacity-50";

export function WizardPage() {
  const { t } = useTranslation();
  const { lang } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { user } = useAuth();
  const seg = lang && isSupported(lang) ? lang : FALLBACK_LANG;

  const { data: wiz } = useQuery({ queryKey: ["wizard"], queryFn: getWizard });
  // Open-source edition (gating off) skips the License step: the step rail hides the license item and goes straight to super-admin/email/branding.
  const { data: licenseCard } = useQuery({ queryKey: ["license"], queryFn: getLicenseCard });
  const rail = licenseCard?.required === false ? RAIL.filter((s) => s.key !== "license") : RAIL;
  const [stepIdx, setStepIdx] = useState(0); // 0=email, 1=branding
  const [toast, setToast] = useState<ToastMsg | null>(null);
  const [busy, setBusy] = useState(false);

  // Email form
  const [presetId, setPresetId] = useState("");
  const [host, setHost] = useState("");
  const [port, setPort] = useState(465);
  const [encryption, setEncryption] = useState<Encryption>("auto");
  const [smtpUser, setSmtpUser] = useState("");
  const [smtpPass, setSmtpPass] = useState("");
  const [fromAddr, setFromAddr] = useState("");
  const [fromName, setFromName] = useState("Terrane");
  const [allowInsecure, setAllowInsecure] = useState(false);
  // Branding form
  const [productName, setProductName] = useState("Terrane");
  const [accent, setAccent] = useState("#0f9b8e");
  const [subtitle, setSubtitle] = useState("");

  // Hydrate from backend state once
  const [hydrated, setHydrated] = useState(false);
  useEffect(() => {
    if (!wiz || hydrated) return;
    if (wiz.completed) {
      navigate(`/${seg}/admin`, { replace: true });
      return;
    }
    setHost(wiz.email.host || "");
    setPort(wiz.email.port || 465);
    setEncryption(wiz.email.encryption || "auto");
    setSmtpUser(wiz.email.username || "");
    setFromAddr(wiz.email.from_address || "");
    setFromName(wiz.email.from_name || "Terrane");
    setAllowInsecure(!!wiz.email.allow_insecure);
    setProductName(wiz.branding.product_name || "Terrane");
    setAccent(wiz.branding.accent_color || "#0f9b8e");
    setSubtitle(wiz.branding.login_subtitle || "");
    setHydrated(true);
  }, [wiz, hydrated, navigate, seg]);

  function err(e: unknown): string {
    if (e instanceof ApiError) {
      // Email failures carry a precise hint (app password / sender mismatch / rate limit, etc.) -> prefer the hint message.
      const hint = (e.details as { hint?: string } | undefined)?.hint;
      if (hint) return t(`wizard.emailHint.${hint}`, { defaultValue: t(`errors.${e.code}`) });
      return t(`errors.${e.code}`);
    }
    return t("errors.SYSTEM_HTTP_ERROR");
  }

  const emailPayload = () => ({
    host, port, encryption, username: smtpUser, password: smtpPass,
    from_address: fromAddr, from_name: fromName || "Terrane", allow_insecure: allowInsecure,
  });

  function applyPreset(id: string) {
    setPresetId(id);
    const p = wiz?.email_presets.find((x) => x.id === id);
    if (!p) return;
    if (p.host) setHost(p.host);
    setPort(p.port);
    setEncryption(p.encryption as Encryption);
    // For providers that lock the sender to the username: the from address follows the username by default (and updates when the username changes).
  }

  async function onSaveEmail(skip: boolean) {
    if (skip) { setStepIdx(1); return; }
    setBusy(true);
    try {
      await saveEmail(emailPayload());
      await qc.invalidateQueries({ queryKey: ["wizard"] });
      setToast({ kind: "success", text: t("wizard.savedEmail") });
      setStepIdx(1);
    } catch (e) {
      setToast({ kind: "error", text: err(e) });
    } finally {
      setBusy(false);
    }
  }

  async function onTestEmail() {
    setBusy(true);
    try {
      await saveEmail(emailPayload());  // Save the current email config before testing the connection
      await testEmail(fromAddr || smtpUser);
      setToast({ kind: "success", text: t("wizard.testSent") });
    } catch (e) {
      setToast({ kind: "error", text: err(e) });
    } finally {
      setBusy(false);
    }
  }

  const selectedPreset = wiz?.email_presets.find((x) => x.id === presetId);

  async function onFinish(skipBranding: boolean) {
    setBusy(true);
    try {
      if (!skipBranding) {
        await saveBranding({ product_name: productName, accent_color: accent,
          login_subtitle: subtitle || null, logo_data: null, support_url: null });
      }
      await completeWizard();
      await qc.invalidateQueries({ queryKey: ["wizard"] });
      navigate(`/${seg}/admin`, { replace: true });
    } catch (e) {
      setToast({ kind: "error", text: err(e) });
    } finally {
      setBusy(false);
    }
  }

  const statusOf = (key: string): "done" | "current" | "pending" => {
    const s = wiz?.steps.find((x) => x.key === key);
    if (key === "done") return "pending";
    if (s) return stepIdx === 0 && key === "branding" ? "pending"
      : stepIdx === 1 && key === "email" ? "done" : s.status;
    return "pending";
  };

  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex items-center justify-between px-8 py-5">
        <Logo />
        <div className="flex items-center gap-2.5">
          <LanguageSelect />
          <span aria-hidden="true" className="h-5 w-px bg-border" />
          <ThemeToggle />
        </div>
      </header>

      <main className="mx-auto grid w-full max-w-3xl flex-1 grid-cols-[180px_1fr] gap-10 px-6 py-6">
        {/* Step rail */}
        <nav className="space-y-3 pt-2">
          {rail.map((s) => {
            const st = statusOf(s.key);
            return (
              <div key={s.key} className="flex items-center gap-2 text-sm">
                {st === "done" ? (
                  <CheckCircle className="size-4 text-accent" weight="fill" />
                ) : (
                  <Circle className={`size-4 ${st === "current" ? "text-accent" : "text-ink-faint"}`}
                    weight={st === "current" ? "fill" : "regular"} />
                )}
                <span className={st === "pending" ? "text-ink-faint" : "text-ink"}>
                  {t(`wizard.step.${s.key}`)}
                </span>
              </div>
            );
          })}
        </nav>

        {/* Current step content */}
        <section>
          <h1 className="text-2xl font-bold tracking-tight text-ink">{t("wizard.title")}</h1>
          <p className="mt-1.5 text-sm text-ink-secondary">
            {t("wizard.welcome", { name: user?.username ?? user?.email ?? "" })}
          </p>

          {stepIdx === 0 && (
            <div className="mt-8 space-y-4">
              <h2 className="text-base font-semibold text-ink">{t("wizard.step.email")}</h2>
              <p className="text-sm text-ink-secondary">{t("wizard.emailDesc")}</p>

              {/* One-click provider presets */}
              <label className="block text-sm font-medium text-ink">
                {t("wizard.provider")}
                <Select className="mt-1.5" value={presetId} onChange={applyPreset}
                  placeholder={t("wizard.providerPick")} disabled={busy}
                  ariaLabel={t("wizard.provider")}
                  options={(wiz?.email_presets ?? []).map((p) => ({ value: p.id, label: p.label }))} />
              </label>
              {selectedPreset?.password_hint && (
                <p className="rounded-(--radius-control) bg-accent-soft px-3 py-2 text-xs text-accent">
                  {selectedPreset.password_hint}
                </p>
              )}

              <div className="grid grid-cols-2 gap-3">
                <label className="col-span-2 text-sm font-medium text-ink">
                  {t("wizard.smtpHost")}
                  <input value={host} onChange={(e) => setHost(e.target.value)}
                    placeholder="smtp.example.com" disabled={busy} className={`mt-1.5 ${field}`} />
                </label>
                <label className="text-sm font-medium text-ink">
                  {t("wizard.smtpPort")}
                  <input type="number" value={port} onChange={(e) => setPort(Number(e.target.value))}
                    disabled={busy} className={`mt-1.5 ${field}`} />
                </label>
                <label className="text-sm font-medium text-ink">
                  {t("wizard.smtpEncryption")}
                  <Select className="mt-1.5" value={encryption}
                    onChange={(v) => setEncryption(v as Encryption)} disabled={busy}
                    ariaLabel={t("wizard.smtpEncryption")}
                    options={[
                      { value: "auto", label: t("wizard.encAuto") },
                      { value: "ssl", label: t("wizard.encSsl") },
                      { value: "starttls", label: t("wizard.encStarttls") },
                      { value: "none", label: t("wizard.encNone") },
                    ]} />
                </label>
                <label className="text-sm font-medium text-ink">
                  {t("wizard.smtpUser")}
                  <input value={smtpUser} onChange={(e) => setSmtpUser(e.target.value)}
                    autoComplete="off" disabled={busy} className={`mt-1.5 ${field}`} />
                </label>
                <label className="text-sm font-medium text-ink">
                  {t("wizard.smtpPass")}
                  <input type="password" value={smtpPass} onChange={(e) => setSmtpPass(e.target.value)}
                    autoComplete="new-password" disabled={busy} className={`mt-1.5 ${field}`} />
                </label>
                <label className="text-sm font-medium text-ink">
                  {t("wizard.smtpFromName")}
                  <input value={fromName} onChange={(e) => setFromName(e.target.value)}
                    placeholder="Terrane" disabled={busy} className={`mt-1.5 ${field}`} />
                </label>
                <label className="text-sm font-medium text-ink">
                  {t("wizard.smtpFrom")}
                  <input value={fromAddr} onChange={(e) => setFromAddr(e.target.value)}
                    placeholder="no-reply@example.com" disabled={busy} className={`mt-1.5 ${field}`} />
                  {selectedPreset?.from_locked && (
                    <span className="mt-1 block text-xs text-ink-faint">{t("wizard.fromLockedHint")}</span>
                  )}
                </label>
                <label className="col-span-2 flex items-center gap-2 pt-1 text-sm text-ink-secondary">
                  <input type="checkbox" checked={allowInsecure}
                    onChange={(e) => setAllowInsecure(e.target.checked)} disabled={busy}
                    className="size-4 accent-[var(--color-accent,#0f9b8e)]" />
                  {t("wizard.allowInsecure")}
                </label>
              </div>
              <div className="flex items-center gap-3 pt-2">
                <button type="button" onClick={onTestEmail} disabled={busy || !host || !fromAddr}
                  className="flex items-center gap-1.5 rounded-(--radius-control) border border-border px-3.5 py-2 text-sm text-ink-secondary hover:bg-canvas hover:text-ink disabled:opacity-50">
                  <PaperPlaneTilt className="size-4" /> {t("wizard.testEmail")}
                </button>
                <span className="flex-1" />
                <button type="button" onClick={() => onSaveEmail(true)} disabled={busy}
                  className="text-sm text-ink-faint hover:text-ink-secondary">
                  {t("wizard.skip")}
                </button>
                <button type="button" onClick={() => onSaveEmail(false)} disabled={busy || !host || !fromAddr}
                  className="rounded-(--radius-control) bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-50">
                  {t("wizard.saveNext")}
                </button>
              </div>
            </div>
          )}

          {stepIdx === 1 && (
            <div className="mt-8 space-y-4">
              <h2 className="text-base font-semibold text-ink">{t("wizard.step.branding")}</h2>
              <p className="text-sm text-ink-secondary">{t("wizard.brandingDesc")}</p>
              <label className="block text-sm font-medium text-ink">
                {t("wizard.productName")}
                <input value={productName} onChange={(e) => setProductName(e.target.value)}
                  disabled={busy} className={`mt-1.5 ${field}`} />
              </label>
              <label className="block text-sm font-medium text-ink">
                {t("wizard.accent")}
                <div className="mt-1.5 flex items-center gap-3">
                  <input type="color" value={accent} onChange={(e) => setAccent(e.target.value)}
                    disabled={busy} className="size-10 cursor-pointer rounded border border-border bg-canvas" />
                  <input value={accent} onChange={(e) => setAccent(e.target.value)}
                    disabled={busy} className={field} />
                </div>
              </label>
              <label className="block text-sm font-medium text-ink">
                {t("wizard.loginSubtitle")}
                <input value={subtitle} onChange={(e) => setSubtitle(e.target.value)}
                  disabled={busy} className={`mt-1.5 ${field}`} />
              </label>
              <div className="flex items-center gap-3 pt-2">
                <button type="button" onClick={() => setStepIdx(0)} disabled={busy}
                  className="text-sm text-ink-faint hover:text-ink-secondary">
                  {t("wizard.back")}
                </button>
                <span className="flex-1" />
                <button type="button" onClick={() => onFinish(true)} disabled={busy}
                  className="text-sm text-ink-faint hover:text-ink-secondary">
                  {t("wizard.skipFinish")}
                </button>
                <button type="button" onClick={() => onFinish(false)} disabled={busy || !productName}
                  className="rounded-(--radius-control) bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-50">
                  {busy ? t("wizard.finishing") : t("wizard.finish")}
                </button>
              </div>
            </div>
          )}
        </section>
      </main>

      <Toast toast={toast} onDone={() => setToast(null)} />
    </div>
  );
}
