/** Reset password —— entered via the ?token= email link to set a new password. On success → go to login. */

import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";

import { FALLBACK_LANG, isSupported } from "@/i18n/langs";
import { resetPassword } from "@/lib/auth";
import { AuthShell, Toast, errorKey, fieldClass, useToast } from "@/pages/auth/_shared";

export function ResetPasswordPage() {
  const { t } = useTranslation();
  const { lang } = useParams();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const seg = lang && isSupported(lang) ? lang : FALLBACK_LANG;
  const token = params.get("token") ?? "";

  const [pw, setPw] = useState("");
  const [confirm, setConfirm] = useState("");
  const [toast, setToast] = useToast();
  const [busy, setBusy] = useState(false);

  const mismatch = confirm !== "" && pw !== confirm;
  const canSubmit = token !== "" && pw.trim() !== "" && pw === confirm;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!canSubmit || busy) return;
    setBusy(true);
    try {
      await resetPassword(token, pw);
      setToast({ kind: "success", text: t("reset.done") });
      setTimeout(() => navigate(`/${seg}/login`, { replace: true }), 1200);
    } catch (err) {
      setToast({ kind: "error", text: t(errorKey(err)) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell>
      <h1 className="text-[28px] font-bold leading-tight tracking-tight text-ink">{t("reset.title")}</h1>
      {token === "" ? (
        <>
          <p className="mt-3 text-sm text-danger">{t("reset.noToken")}</p>
          <Link to={`/${seg}/forgot-password`}
            className="mt-8 block w-full rounded-(--radius-control) bg-accent px-4 py-2.5 text-center text-sm font-medium text-white hover:bg-accent-hover">
            {t("reset.requestNew")}
          </Link>
        </>
      ) : (
        <form className="mt-8 space-y-5" onSubmit={submit}>
          <div>
            <label className="mb-1.5 block text-sm font-medium text-ink">{t("reset.newPassword")}</label>
            <input type="password" autoComplete="new-password" value={pw}
              onChange={(e) => setPw(e.target.value)} placeholder={t("register.passwordPlaceholder")}
              disabled={busy} className={fieldClass} />
            <p className="mt-1.5 text-xs text-ink-faint">{t("register.policy")}</p>
          </div>
          <div>
            <label className="mb-1.5 block text-sm font-medium text-ink">{t("reset.confirm")}</label>
            <input type="password" autoComplete="new-password" value={confirm}
              onChange={(e) => setConfirm(e.target.value)} disabled={busy} className={fieldClass} />
            {mismatch && <p className="mt-1.5 text-xs text-danger">{t("reset.mismatch")}</p>}
          </div>
          <button type="submit" disabled={busy || !canSubmit}
            className="w-full rounded-(--radius-control) bg-accent px-4 py-2.5 text-sm font-medium text-white transition hover:bg-accent-hover disabled:opacity-50">
            {busy ? t("reset.submitting") : t("reset.submit")}
          </button>
        </form>
      )}
      <Toast toast={toast} onDone={() => setToast(null)} />
    </AuthShell>
  );
}
