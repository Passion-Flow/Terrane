/** Login page —— email + password + 2FA (shown conditionally: only after receiving AUTH_2FA_REQUIRED).
 *  Submit: login → refresh() (fetches /me) → navigate to /<lang>/admin; on failure, translate the error by code.
 *  Visually aligned with the activate page (same header + centered narrow column + top-right toast). */

import { CheckCircle, Eye, EyeSlash, XCircle } from "@phosphor-icons/react";
import { useEffect, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router";

import { useAuth } from "@/auth/AuthContext";
import { useBranding } from "@/branding/BrandingContext";
import { LanguageSelect } from "@/components/LanguageSelect";
import { Logo } from "@/components/Logo";
import { ThemeToggle } from "@/components/ThemeToggle";
import { FALLBACK_LANG, isSupported } from "@/i18n/langs";
import { ApiError } from "@/lib/api";
import { login } from "@/lib/auth";

function errorKey(err: unknown): string {
  const code = err instanceof ApiError ? err.code : "SYSTEM_HTTP_ERROR";
  return `errors.${code}`;
}

/* ── toast (top-right, auto-dismissing) —— same as the activate page ── */

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
  const [toast, setToast] = useState<ToastMsg | null>(null);
  const [busy, setBusy] = useState(false);

  const canSubmit =
    email.trim() !== "" && password.trim() !== "" && (!need2fa || code.trim() !== "");

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!canSubmit || busy) return;
    setBusy(true);
    setToast(null);
    try {
      await login({ email: email.trim(), password, code: code.trim() || undefined });
      await refresh();
      navigate(`/${seg}/admin`, { replace: true });
    } catch (err) {
      // First time without 2FA: reveal the verification-code input (not a hard error; the message uses the AUTH_2FA_REQUIRED copy).
      if (err instanceof ApiError && err.code === "AUTH_2FA_REQUIRED") {
        setNeed2fa(true);
      }
      setToast({ kind: "error", text: t(errorKey(err)) });
    } finally {
      setBusy(false);
    }
  }

  // Taller input fields, restrained borders, focus accent ring (teal accent).
  const fieldClass =
    "w-full rounded-(--radius-control) border border-border bg-canvas px-3.5 py-2.5 text-sm text-ink outline-none transition placeholder:text-ink-faint focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/40 disabled:opacity-50";

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

      {/* No card border; content centered into a narrow column, with a large heading + welcome message + form */}
      <main className="flex flex-1 items-center justify-center px-4 pb-24">
        <div className="w-full max-w-[400px]">
          {loginLogo && <img src={loginLogo} alt="" className="mb-5 h-11 w-auto object-contain" />}
          <h1 className="text-[28px] font-bold leading-tight tracking-tight text-ink">
            {t("login.title")}
          </h1>
          <p className="mt-2 text-sm text-ink-secondary">{loginSubtitle || t("login.welcome")}</p>

          <form className="mt-8 space-y-5" onSubmit={submit}>
            <div>
              <label htmlFor="email" className="mb-1.5 block text-sm font-medium text-ink">
                {t("login.email")}
              </label>
              <input
                id="email"
                type="email"
                autoComplete="username"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder={t("login.emailPlaceholder")}
                disabled={busy}
                className={fieldClass}
              />
            </div>

            <div>
              <label htmlFor="password" className="mb-1.5 block text-sm font-medium text-ink">
                {t("login.password")}
              </label>
              <div className="relative">
                <input
                  id="password"
                  type={showPw ? "text" : "password"}
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={t("login.passwordPlaceholder")}
                  disabled={busy}
                  className={`${fieldClass} pe-10`}
                />
                <button
                  type="button"
                  onClick={() => setShowPw((v) => !v)}
                  aria-label={t(showPw ? "login.hidePassword" : "login.showPassword")}
                  className="absolute inset-y-0 end-0 flex items-center pe-3 text-ink-faint hover:text-ink-secondary"
                >
                  {showPw ? <EyeSlash className="size-[18px]" /> : <Eye className="size-[18px]" />}
                </button>
              </div>
            </div>

            {need2fa && (
              <div>
                <label htmlFor="code" className="mb-1.5 block text-sm font-medium text-ink">
                  {t("login.code")}
                </label>
                <input
                  id="code"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  placeholder={t("login.codeHint")}
                  disabled={busy}
                  className={fieldClass}
                />
              </div>
            )}

            <button
              type="submit"
              disabled={busy || !canSubmit}
              className="mt-1 w-full rounded-(--radius-control) bg-accent px-4 py-2.5 text-sm font-medium text-white transition hover:bg-accent-hover focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-50"
            >
              {busy ? t("login.submitting") : t("login.submit")}
            </button>
          </form>
        </div>
      </main>

      <Toast toast={toast} onDone={() => setToast(null)} />
    </div>
  );
}
