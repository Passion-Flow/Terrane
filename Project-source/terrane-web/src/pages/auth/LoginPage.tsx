/** 登录页 —— 邮箱 + 密码（+2FA 条件位）。成功 → refresh() → /<lang>/。 */

import { Eye, EyeSlash } from "@phosphor-icons/react";
import { useEffect, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams } from "react-router";

import { useAuth } from "@/auth/AuthContext";
import { useBranding } from "@/branding/BrandingContext";
import { FALLBACK_LANG, isSupported } from "@/i18n/langs";
import { ApiError, request } from "@/lib/api";
import { apiBase } from "@/lib/config";
import { login } from "@/lib/auth";
import { AuthShell, Toast, errorKey, fieldClass, useToast } from "@/pages/auth/_shared";

export function LoginPage() {
  const { t } = useTranslation();
  const { lang } = useParams();
  const navigate = useNavigate();
  const { refresh } = useAuth();
  const { login_subtitle: loginSubtitle, login_logo: loginLogo } = useBranding();
  const seg = lang && isSupported(lang) ? lang : FALLBACK_LANG;

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [code, setCode] = useState("");
  const [need2fa, setNeed2fa] = useState(false);
  const [toast, setToast] = useToast();
  const [busy, setBusy] = useState(false);
  const [sso, setSso] = useState<{ enabled: boolean; label: string } | null>(null);

  useEffect(() => {
    request<{ data: { enabled: boolean; label: string } }>("/api/v1/auth/sso/status", { credentials: "include" })
      .then((r) => setSso(r.data)).catch(() => setSso(null));
  }, []);

  const canSubmit = email.trim() !== "" && password.trim() !== "" && (!need2fa || code.trim() !== "");

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!canSubmit || busy) return;
    setBusy(true);
    setToast(null);
    try {
      await login({ email: email.trim(), password, code: code.trim() || undefined });
      await refresh();
      navigate(`/${seg}/`, { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.code === "AUTH_2FA_REQUIRED") setNeed2fa(true);
      setToast({ kind: "error", text: t(errorKey(err)) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell>
      {loginLogo && <img src={loginLogo} alt="" className="mb-5 h-11 w-auto object-contain" />}
      <h1 className="text-[28px] font-bold leading-tight tracking-tight text-ink">{t("login.title")}</h1>
      <p className="mt-2 text-sm text-ink-secondary">{loginSubtitle || t("login.welcome")}</p>
      <form className="mt-8 space-y-5" onSubmit={submit}>
        <div>
          <label htmlFor="email" className="mb-1.5 block text-sm font-medium text-ink">{t("login.email")}</label>
          <input id="email" type="email" autoComplete="username" value={email}
            onChange={(e) => setEmail(e.target.value)} placeholder={t("login.emailPlaceholder")}
            disabled={busy} className={fieldClass} />
        </div>
        <div>
          <label htmlFor="password" className="mb-1.5 block text-sm font-medium text-ink">{t("login.password")}</label>
          <div className="relative">
            <input id="password" type={showPw ? "text" : "password"} autoComplete="current-password"
              value={password} onChange={(e) => setPassword(e.target.value)}
              placeholder={t("login.passwordPlaceholder")} disabled={busy} className={`${fieldClass} pe-10`} />
            <button type="button" onClick={() => setShowPw((v) => !v)}
              aria-label={t(showPw ? "login.hidePassword" : "login.showPassword")}
              className="absolute inset-y-0 end-0 flex items-center pe-3 text-ink-faint hover:text-ink-secondary">
              {showPw ? <EyeSlash className="size-[18px]" /> : <Eye className="size-[18px]" />}
            </button>
          </div>
          <div className="mt-1.5 text-end">
            <Link to={`/${seg}/forgot-password`} className="text-xs text-accent hover:underline">
              {t("login.forgot")}
            </Link>
          </div>
        </div>
        {need2fa && (
          <div>
            <label htmlFor="code" className="mb-1.5 block text-sm font-medium text-ink">{t("login.code")}</label>
            <input id="code" inputMode="numeric" autoComplete="one-time-code" value={code}
              onChange={(e) => setCode(e.target.value)} placeholder={t("login.codeHint")}
              disabled={busy} className={fieldClass} />
          </div>
        )}
        <button type="submit" disabled={busy || !canSubmit}
          className="mt-1 w-full rounded-(--radius-control) bg-accent px-4 py-2.5 text-sm font-medium text-white transition hover:bg-accent-hover focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-50">
          {busy ? t("login.submitting") : t("login.submit")}
        </button>
      </form>
      {sso?.enabled && (
        <div className="mt-4">
          <div className="flex items-center gap-3 text-xs text-ink-faint">
            <span className="h-px flex-1 bg-border" />{t("login.or")}<span className="h-px flex-1 bg-border" />
          </div>
          <button type="button" onClick={() => { window.location.href = `${apiBase()}/api/v1/auth/sso/login`; }}
            className="mt-4 w-full rounded-(--radius-control) border border-border px-4 py-2.5 text-sm font-medium text-ink transition hover:bg-canvas">
            {t("login.ssoLogin", { provider: sso.label })}
          </button>
        </div>
      )}
      <p className="mt-6 text-center text-sm text-ink-secondary">
        {t("login.noAccount")}{" "}
        <Link to={`/${seg}/register`} className="font-medium text-accent hover:underline">{t("login.toRegister")}</Link>
      </p>
      <Toast toast={toast} onDone={() => setToast(null)} />
    </AuthShell>
  );
}
