/** 强制改密页 —— 初始化向导「超管」步：出厂超管密码=邮箱，首登必须改密才放行控制台。
 *  当前密码 + 新密码 + 确认；成功后 refresh()（must_change_password 清零）→ 进 /admin。
 *  视觉与 LoginPage 同款（header + 居中窄列 + 右上 toast）。 */

import { CheckCircle, Eye, EyeSlash, XCircle } from "@phosphor-icons/react";
import { useEffect, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router";

import { useAuth } from "@/auth/AuthContext";
import { LanguageSelect } from "@/components/LanguageSelect";
import { Logo } from "@/components/Logo";
import { ThemeToggle } from "@/components/ThemeToggle";
import { FALLBACK_LANG, isSupported } from "@/i18n/langs";
import { ApiError } from "@/lib/api";
import { changePassword } from "@/lib/auth";

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

export function ChangePasswordPage() {
  const { t } = useTranslation();
  const { lang } = useParams();
  const navigate = useNavigate();
  const { refresh, logout } = useAuth();
  const seg = lang && isSupported(lang) ? lang : FALLBACK_LANG;

  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [toast, setToast] = useState<ToastMsg | null>(null);
  const [busy, setBusy] = useState(false);

  const mismatch = confirm !== "" && next !== confirm;
  const canSubmit = current.trim() !== "" && next.trim() !== "" && next === confirm;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!canSubmit || busy) return;
    setBusy(true);
    setToast(null);
    try {
      await changePassword({ current_password: current, new_password: next });
      await refresh();
      navigate(`/${seg}/admin`, { replace: true });
    } catch (err) {
      const code = err instanceof ApiError ? err.code : "SYSTEM_HTTP_ERROR";
      setToast({ kind: "error", text: t(`errors.${code}`) });
    } finally {
      setBusy(false);
    }
  }

  async function onCancel() {
    await logout();
    navigate(`/${seg}/login`, { replace: true });
  }

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

      <main className="flex flex-1 items-center justify-center px-4 pb-24">
        <div className="w-full max-w-[400px]">
          <h1 className="text-[28px] font-bold leading-tight tracking-tight text-ink">
            {t("changePassword.title")}
          </h1>
          <p className="mt-2 text-sm text-ink-secondary">{t("changePassword.desc")}</p>

          <form className="mt-8 space-y-5" onSubmit={submit}>
            <div>
              <label htmlFor="current" className="mb-1.5 block text-sm font-medium text-ink">
                {t("changePassword.current")}
              </label>
              <input
                id="current"
                type={showPw ? "text" : "password"}
                autoComplete="current-password"
                value={current}
                onChange={(e) => setCurrent(e.target.value)}
                placeholder={t("changePassword.currentPlaceholder")}
                disabled={busy}
                className={fieldClass}
              />
            </div>

            <div>
              <label htmlFor="next" className="mb-1.5 block text-sm font-medium text-ink">
                {t("changePassword.next")}
              </label>
              <div className="relative">
                <input
                  id="next"
                  type={showPw ? "text" : "password"}
                  autoComplete="new-password"
                  value={next}
                  onChange={(e) => setNext(e.target.value)}
                  placeholder={t("changePassword.nextPlaceholder")}
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
              <p className="mt-1.5 text-xs text-ink-faint">{t("changePassword.policy")}</p>
            </div>

            <div>
              <label htmlFor="confirm" className="mb-1.5 block text-sm font-medium text-ink">
                {t("changePassword.confirm")}
              </label>
              <input
                id="confirm"
                type={showPw ? "text" : "password"}
                autoComplete="new-password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                placeholder={t("changePassword.confirmPlaceholder")}
                disabled={busy}
                className={fieldClass}
              />
              {mismatch && (
                <p className="mt-1.5 text-xs text-danger">{t("changePassword.mismatch")}</p>
              )}
            </div>

            <button
              type="submit"
              disabled={busy || !canSubmit}
              className="mt-1 w-full rounded-(--radius-control) bg-accent px-4 py-2.5 text-sm font-medium text-white transition hover:bg-accent-hover focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-50"
            >
              {busy ? t("changePassword.submitting") : t("changePassword.submit")}
            </button>
            <button
              type="button"
              onClick={onCancel}
              className="w-full text-center text-sm text-ink-faint hover:text-ink-secondary"
            >
              {t("changePassword.cancel")}
            </button>
          </form>
        </div>
      </main>

      <Toast toast={toast} onDone={() => setToast(null)} />
    </div>
  );
}
