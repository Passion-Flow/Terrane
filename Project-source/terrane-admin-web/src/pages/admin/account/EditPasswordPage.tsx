/** Account security → Change password (personal; self-service change of your own admin password).
 *  Reuses /auth/change-password (verify old password → policy check → persist → rotate session and issue a new cookie, no re-login required). */

import { useState } from "react";
import { useTranslation } from "react-i18next";

import { useAuth } from "@/auth/AuthContext";
import { ApiError } from "@/lib/api";
import { changePassword } from "@/lib/auth";
import { field, SettingsShell, Toast, toErrText, type ToastMsg } from "@/pages/admin/settings/_shared";

export function EditPasswordPage() {
  const { t } = useTranslation();
  const { refresh } = useAuth();
  const [toast, setToast] = useState<ToastMsg | null>(null);
  const [busy, setBusy] = useState(false);
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");

  const mismatch = confirm !== "" && next !== confirm;
  const canSave = !!current && !!next && next === confirm;

  async function onSave() {
    if (!canSave || busy) return;
    setBusy(true);
    try {
      await changePassword({ current_password: current, new_password: next });
      await refresh();
      setCurrent(""); setNext(""); setConfirm("");
      setToast({ kind: "success", text: t("account.password.saved") });
    } catch (e) {
      // The "passwords don't match" case is caught on the front-end; here the main errors are a wrong old password or a policy violation.
      setToast({ kind: "error", text: e instanceof ApiError ? t(`errors.${e.code}`) : toErrText(e, t) });
    } finally { setBusy(false); }
  }

  return (
    <SettingsShell title={t("account.password.title")} desc={t("account.password.desc")}>
      <section className="max-w-md rounded-xl border border-border/70 bg-surface/40 p-5">
        <div className="space-y-4">
          <label className="block text-sm font-medium text-ink">{t("account.password.current")}
            <input type="password" value={current} onChange={(e) => setCurrent(e.target.value)}
              autoComplete="current-password" disabled={busy} className={`mt-1.5 ${field}`} /></label>
          <label className="block text-sm font-medium text-ink">{t("account.password.next")}
            <input type="password" value={next} onChange={(e) => setNext(e.target.value)}
              autoComplete="new-password" disabled={busy} className={`mt-1.5 ${field}`} />
            <span className="mt-1 block text-xs font-normal text-ink-faint">{t("account.password.policyHint")}</span></label>
          <label className="block text-sm font-medium text-ink">{t("account.password.confirm")}
            <input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)}
              autoComplete="new-password" disabled={busy} className={`mt-1.5 ${field}`} />
            {mismatch && <span className="mt-1 block text-xs font-normal text-danger">{t("account.password.mismatch")}</span>}</label>

          <div className="flex items-center pt-1">
            <span className="flex-1" />
            <button type="button" onClick={onSave} disabled={busy || !canSave}
              className="rounded-(--radius-control) bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-50">
              {busy ? t("common.saving") : t("common.save")}</button>
          </div>
        </div>
      </section>
      <Toast toast={toast} onDone={() => setToast(null)} />
    </SettingsShell>
  );
}
