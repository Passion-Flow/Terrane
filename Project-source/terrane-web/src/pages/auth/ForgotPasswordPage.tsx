/** 忘记密码 —— 输入邮箱请求重置链接（防枚举：恒提示已发送）。 */

import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router";

import { FALLBACK_LANG, isSupported } from "@/i18n/langs";
import { requestReset } from "@/lib/auth";
import { AuthShell, Toast, errorKey, fieldClass, useToast } from "@/pages/auth/_shared";

export function ForgotPasswordPage() {
  const { t } = useTranslation();
  const { lang } = useParams();
  const seg = lang && isSupported(lang) ? lang : FALLBACK_LANG;

  const [email, setEmail] = useState("");
  const [toast, setToast] = useToast();
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (email.trim() === "" || busy) return;
    setBusy(true);
    try {
      await requestReset(email.trim());
      setDone(true);
    } catch (err) {
      setToast({ kind: "error", text: t(errorKey(err)) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell>
      <h1 className="text-[28px] font-bold leading-tight tracking-tight text-ink">{t("forgot.title")}</h1>
      {done ? (
        <>
          <p className="mt-3 text-sm text-ink-secondary">{t("forgot.sent", { email })}</p>
          <Link to={`/${seg}/login`}
            className="mt-8 block w-full rounded-(--radius-control) bg-accent px-4 py-2.5 text-center text-sm font-medium text-white hover:bg-accent-hover">
            {t("register.toLogin")}
          </Link>
        </>
      ) : (
        <>
          <p className="mt-2 text-sm text-ink-secondary">{t("forgot.desc")}</p>
          <form className="mt-8 space-y-5" onSubmit={submit}>
            <input type="email" autoComplete="username" value={email}
              onChange={(e) => setEmail(e.target.value)} placeholder={t("login.emailPlaceholder")}
              disabled={busy} className={fieldClass} />
            <button type="submit" disabled={busy || email.trim() === ""}
              className="w-full rounded-(--radius-control) bg-accent px-4 py-2.5 text-sm font-medium text-white transition hover:bg-accent-hover disabled:opacity-50">
              {busy ? t("forgot.submitting") : t("forgot.submit")}
            </button>
          </form>
          <p className="mt-6 text-center text-sm text-ink-secondary">
            <Link to={`/${seg}/login`} className="font-medium text-accent hover:underline">{t("forgot.back")}</Link>
          </p>
        </>
      )}
      <Toast toast={toast} onDone={() => setToast(null)} />
    </AuthShell>
  );
}
