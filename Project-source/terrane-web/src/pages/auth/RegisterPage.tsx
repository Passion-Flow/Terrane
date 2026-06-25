/** Register page — email + password + username. On success, prompts the user to verify their email (email verification is enforced out of the box). */

import { Eye, EyeSlash } from "@phosphor-icons/react";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router";

import { FALLBACK_LANG, isSupported } from "@/i18n/langs";
import { register } from "@/lib/auth";
import { AuthShell, Toast, errorKey, fieldClass, useToast } from "@/pages/auth/_shared";

export function RegisterPage() {
  const { t } = useTranslation();
  const { lang } = useParams();
  const seg = lang && isSupported(lang) ? lang : FALLBACK_LANG;

  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [toast, setToast] = useToast();
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  const canSubmit = email.trim() !== "" && password.trim() !== "";

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!canSubmit || busy) return;
    setBusy(true);
    setToast(null);
    try {
      await register({ email: email.trim(), password, username: username.trim() || undefined });
      setDone(true);
    } catch (err) {
      setToast({ kind: "error", text: t(errorKey(err)) });
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <AuthShell>
        <h1 className="text-[28px] font-bold leading-tight tracking-tight text-ink">{t("register.checkEmailTitle")}</h1>
        <p className="mt-3 text-sm text-ink-secondary">{t("register.checkEmailDesc", { email })}</p>
        <Link to={`/${seg}/login`}
          className="mt-8 block w-full rounded-(--radius-control) bg-accent px-4 py-2.5 text-center text-sm font-medium text-white hover:bg-accent-hover">
          {t("register.toLogin")}
        </Link>
      </AuthShell>
    );
  }

  return (
    <AuthShell>
      <h1 className="text-[28px] font-bold leading-tight tracking-tight text-ink">{t("register.title")}</h1>
      <p className="mt-2 text-sm text-ink-secondary">{t("register.welcome")}</p>
      <form className="mt-8 space-y-5" onSubmit={submit}>
        <div>
          <label htmlFor="email" className="mb-1.5 block text-sm font-medium text-ink">{t("login.email")}</label>
          <input id="email" type="email" autoComplete="username" value={email}
            onChange={(e) => setEmail(e.target.value)} placeholder={t("login.emailPlaceholder")}
            disabled={busy} className={fieldClass} />
        </div>
        <div>
          <label htmlFor="username" className="mb-1.5 block text-sm font-medium text-ink">{t("register.username")}</label>
          <input id="username" autoComplete="nickname" value={username}
            onChange={(e) => setUsername(e.target.value)} placeholder={t("register.usernamePlaceholder")}
            disabled={busy} className={fieldClass} />
        </div>
        <div>
          <label htmlFor="password" className="mb-1.5 block text-sm font-medium text-ink">{t("login.password")}</label>
          <div className="relative">
            <input id="password" type={showPw ? "text" : "password"} autoComplete="new-password"
              value={password} onChange={(e) => setPassword(e.target.value)}
              placeholder={t("register.passwordPlaceholder")} disabled={busy} className={`${fieldClass} pe-10`} />
            <button type="button" onClick={() => setShowPw((v) => !v)}
              aria-label={t(showPw ? "login.hidePassword" : "login.showPassword")}
              className="absolute inset-y-0 end-0 flex items-center pe-3 text-ink-faint hover:text-ink-secondary">
              {showPw ? <EyeSlash className="size-[18px]" /> : <Eye className="size-[18px]" />}
            </button>
          </div>
          <p className="mt-1.5 text-xs text-ink-faint">{t("register.policy")}</p>
        </div>
        <button type="submit" disabled={busy || !canSubmit}
          className="mt-1 w-full rounded-(--radius-control) bg-accent px-4 py-2.5 text-sm font-medium text-white transition hover:bg-accent-hover disabled:opacity-50">
          {busy ? t("register.submitting") : t("register.submit")}
        </button>
      </form>
      <p className="mt-6 text-center text-sm text-ink-secondary">
        {t("register.hasAccount")}{" "}
        <Link to={`/${seg}/login`} className="font-medium text-accent hover:underline">{t("register.toLogin")}</Link>
      </p>
      <Toast toast={toast} onDone={() => setToast(null)} />
    </AuthShell>
  );
}
