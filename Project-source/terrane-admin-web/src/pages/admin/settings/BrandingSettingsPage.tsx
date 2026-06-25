/** Branding & appearance (top-level page) — aligned with Dify's breakdown: app title / console logo / login-page logo / favicon / accent color / login subtitle / support link.
 *  After saving, the site-wide branding (logo / title / favicon / accent color) refreshes immediately. Images are stored as data URIs, ≤700KB (within the backend's 1MB limit). */

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { useAuth } from "@/auth/AuthContext";
import { LogoMarkDefault } from "@/components/Logo";
import { updateBranding, useSettings } from "@/lib/settings";
import { field, SettingsShell, Toast, toErrText, type ToastMsg } from "@/pages/admin/settings/_shared";

function Card({ title, usage, children }: { title: string; usage: string; children: ReactNode }) {
  return (
    <section className="rounded-xl border border-border/70 bg-surface/40 p-5">
      <h2 className="text-base font-semibold text-ink">{title}</h2>
      <p className="mt-1 text-[13px] text-ink-secondary">{usage}</p>
      <div className="mt-4">{children}</div>
    </section>
  );
}

/** Image upload field: preview (custom or placeholder) + upload + remove. */
function LogoField({ value, placeholder, canWrite, busy, onPick, onRemove }: {
  value: string | null; placeholder: ReactNode; canWrite: boolean; busy: boolean;
  onPick: (e: React.ChangeEvent<HTMLInputElement>) => void; onRemove: () => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-3">
      <span className="flex size-12 shrink-0 items-center justify-center overflow-hidden rounded-(--radius-control) border border-border bg-canvas">
        {value ? <img src={value} alt="" className="size-full object-contain" /> : placeholder}
      </span>
      {canWrite && (
        <label className="cursor-pointer rounded-(--radius-control) border border-border px-3 py-1.5 text-[13px] text-ink-secondary transition hover:bg-canvas hover:text-ink">
          {t("settings.logoUpload")}
          <input type="file" accept="image/png,image/jpeg,image/svg+xml,image/webp,image/x-icon"
            className="hidden" disabled={busy} onChange={onPick} />
        </label>
      )}
      {canWrite && value && (
        <button type="button" onClick={onRemove} disabled={busy}
          className="text-[13px] text-ink-faint transition hover:text-danger">{t("settings.logoRemove")}</button>
      )}
    </div>
  );
}

export function BrandingSettingsPage() {
  const { t } = useTranslation();
  const { has } = useAuth();
  const qc = useQueryClient();
  const query = useSettings();
  const canWrite = has("system.settings.write");
  const ro = !canWrite;

  const [toast, setToast] = useState<ToastMsg | null>(null);
  const [busy, setBusy] = useState(false);

  const [productName, setProductName] = useState("Terrane");
  const [accent, setAccent] = useState("#0f9b8e");
  const [subtitle, setSubtitle] = useState("");
  const [supportUrl, setSupportUrl] = useState("");
  const [logoData, setLogoData] = useState<string | null>(null);     // Console logo
  const [loginLogo, setLoginLogo] = useState<string | null>(null);   // Login-page logo
  const [favicon, setFavicon] = useState<string | null>(null);       // Site favicon

  const [hydrated, setHydrated] = useState(false);
  useEffect(() => {
    const s = query.data;
    if (!s || hydrated) return;
    setProductName(s.branding.product_name || "Terrane");
    setAccent(s.branding.accent_color || "#0f9b8e");
    setSubtitle(s.branding.login_subtitle || "");
    setSupportUrl(s.branding.support_url || "");
    setLogoData(s.branding.logo_data ?? null);
    setLoginLogo(s.branding.login_logo ?? null);
    setFavicon(s.branding.favicon ?? null);
    setHydrated(true);
  }, [query.data, hydrated]);

  // Read the image as a data URI; base64 inflates size by 1.33×, and the backend cap is 1MB → the source image must be ≤ 700KB.
  function reader(set: (v: string | null) => void) {
    return (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      e.target.value = "";
      if (!file) return;
      if (file.size > 700_000) { setToast({ kind: "error", text: t("settings.logoTooLarge") }); return; }
      const r = new FileReader();
      r.onload = () => set(typeof r.result === "string" ? r.result : null);
      r.readAsDataURL(file);
    };
  }

  async function onSave() {
    setBusy(true);
    try {
      await updateBranding({
        product_name: productName, accent_color: accent,
        login_subtitle: subtitle || null, support_url: supportUrl || null,
        logo_data: logoData, login_logo: loginLogo, favicon,
      });
      await qc.invalidateQueries({ queryKey: ["settings"] });
      await qc.invalidateQueries({ queryKey: ["branding"] });  // Immediately refresh logo/title/favicon/accent color
      setToast({ kind: "success", text: t("settings.savedBranding") });
    } catch (e) { setToast({ kind: "error", text: toErrText(e, t) }); }
    finally { setBusy(false); }
  }

  return (
    <SettingsShell title={t("settings.branding.title")} desc={t("settings.branding.desc")}>
      <div className="space-y-5">
        <Card title={t("settings.branding.appTitle")} usage={t("settings.branding.appTitleUsage")}>
          <input value={productName} onChange={(e) => setProductName(e.target.value)} maxLength={50}
            disabled={ro || busy} className={`max-w-md ${field}`} />
        </Card>

        <Card title={t("settings.branding.consoleLogo")} usage={t("settings.branding.consoleLogoUsage")}>
          <LogoField value={logoData} placeholder={<LogoMarkDefault size={34} />} canWrite={canWrite} busy={busy}
            onPick={reader(setLogoData)} onRemove={() => setLogoData(null)} />
        </Card>

        <Card title={t("settings.branding.loginLogo")} usage={t("settings.branding.loginLogoUsage")}>
          <LogoField value={loginLogo} placeholder={<LogoMarkDefault size={34} />} canWrite={canWrite} busy={busy}
            onPick={reader(setLoginLogo)} onRemove={() => setLoginLogo(null)} />
        </Card>

        <Card title={t("settings.branding.favicon")} usage={t("settings.branding.faviconUsage")}>
          <LogoField value={favicon} placeholder={<img src="/favicon.svg" alt="" className="size-6" />}
            canWrite={canWrite} busy={busy} onPick={reader(setFavicon)} onRemove={() => setFavicon(null)} />
        </Card>

        <Card title={t("wizard.accent")} usage={t("settings.branding.accentUsage")}>
          <div className="flex items-center gap-3">
            <input type="color" value={accent} onChange={(e) => setAccent(e.target.value)}
              disabled={ro || busy} className="size-10 cursor-pointer rounded border border-border bg-canvas" />
            <input value={accent} onChange={(e) => setAccent(e.target.value)}
              disabled={ro || busy} className={`max-w-[12rem] ${field}`} />
          </div>
        </Card>

        <Card title={t("wizard.loginSubtitle")} usage={t("settings.branding.subtitleUsage")}>
          <input value={subtitle} onChange={(e) => setSubtitle(e.target.value)}
            disabled={ro || busy} className={`max-w-md ${field}`} />
        </Card>

        <Card title={t("settings.supportUrl")} usage={t("settings.branding.supportUsage")}>
          <input value={supportUrl} onChange={(e) => setSupportUrl(e.target.value)}
            placeholder="https://support.example.com" disabled={ro || busy} className={`max-w-md ${field}`} />
        </Card>

        {canWrite && (
          <div className="flex items-center">
            <span className="flex-1" />
            <button type="button" onClick={onSave} disabled={busy || !productName || !hydrated}
              className="rounded-(--radius-control) bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-50">
              {busy ? t("common.saving") : t("common.save")}</button>
          </div>
        )}
      </div>
      <Toast toast={toast} onDone={() => setToast(null)} />
    </SettingsShell>
  );
}
