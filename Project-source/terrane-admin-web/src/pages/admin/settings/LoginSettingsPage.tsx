/** 设置 → 登录设置。登录保护(失败锁定) + 会话时长——真接到 ratelimit / session 执行点。
 *  与 密码策略 共用 system_settings['security']（GET/PATCH /settings/security 全量），本页只编辑登录/会话子集。
 *  后续可在此加：登录方式开关(邮密/验证码)、SSO 启用等(对齐 Dify Login Settings)。 */

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { useAuth } from "@/auth/AuthContext";
import { NumberStepper } from "@/components/NumberStepper";
import { updateSecurity, useSecurity } from "@/lib/settings";
import { SettingsShell, Toast, toErrText, type ToastMsg } from "@/pages/admin/settings/_shared";

function Card({ title, desc, children }: { title: string; desc: string; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-border/70 bg-surface/40 p-5">
      <h2 className="text-base font-semibold text-ink">{title}</h2>
      <p className="mt-1 text-[13px] text-ink-secondary">{desc}</p>
      <div className="mt-4">{children}</div>
    </section>
  );
}

export function LoginSettingsPage() {
  const { t } = useTranslation();
  const { has } = useAuth();
  const qc = useQueryClient();
  const query = useSecurity();
  const canWrite = has("system.settings.write");
  const ro = !canWrite;

  const [toast, setToast] = useState<ToastMsg | null>(null);
  const [busy, setBusy] = useState(false);
  const [lockThreshold, setLockThreshold] = useState(5);
  const [lockMinutes, setLockMinutes] = useState(15);
  const [sessionDays, setSessionDays] = useState(7);

  const [hydrated, setHydrated] = useState(false);
  useEffect(() => {
    const s = query.data;
    if (!s || hydrated) return;
    setLockThreshold(s.login_lock_threshold);
    setLockMinutes(Math.round(s.login_lock_seconds / 60));
    setSessionDays(Math.round(s.session_absolute_ttl_seconds / 86400));
    setHydrated(true);
  }, [query.data, hydrated]);

  async function onSave() {
    if (!query.data) return;
    setBusy(true);
    try {
      // 全量提交：保留密码子集不变，只改登录/会话子集。
      await updateSecurity({
        ...query.data,
        login_lock_threshold: lockThreshold,
        login_lock_seconds: lockMinutes * 60,
        session_absolute_ttl_seconds: sessionDays * 86400,
      });
      await qc.invalidateQueries({ queryKey: ["settings", "security"] });
      setToast({ kind: "success", text: t("settings.savedSecurity") });
    } catch (e) { setToast({ kind: "error", text: toErrText(e, t) }); }
    finally { setBusy(false); }
  }

  return (
    <SettingsShell title={t("settings.login.title")} desc={t("settings.login.desc")}>
      <div className="space-y-5">
        <Card title={t("settings.security.lockTitle")} desc={t("settings.security.lockDesc")}>
          <div className="grid grid-cols-2 gap-4">
            <label className="text-sm font-medium text-ink">{t("settings.security.lockThreshold")}
              <NumberStepper className="mt-1.5" value={lockThreshold} onChange={setLockThreshold}
                min={3} max={50} disabled={ro || busy} />
              <span className="mt-1 block text-xs font-normal text-ink-faint">{t("settings.security.lockThresholdHint")}</span>
            </label>
            <label className="text-sm font-medium text-ink">{t("settings.security.lockMinutes")}
              <NumberStepper className="mt-1.5" value={lockMinutes} onChange={setLockMinutes}
                min={1} max={1440} disabled={ro || busy} />
              <span className="mt-1 block text-xs font-normal text-ink-faint">{t("settings.security.lockMinutesHint")}</span>
            </label>
          </div>
        </Card>

        <Card title={t("settings.security.sessionTitle")} desc={t("settings.security.sessionDesc")}>
          <label className="block max-w-[12rem] text-sm font-medium text-ink">{t("settings.security.sessionDays")}
            <NumberStepper className="mt-1.5" value={sessionDays} onChange={setSessionDays}
              min={1} max={365} disabled={ro || busy} />
            <span className="mt-1 block text-xs font-normal text-ink-faint">{t("settings.security.sessionDaysHint")}</span>
          </label>
        </Card>

        {canWrite && (
          <div className="flex items-center">
            <span className="flex-1" />
            <button type="button" onClick={onSave} disabled={busy || !hydrated}
              className="rounded-(--radius-control) bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-50">
              {busy ? t("common.saving") : t("common.save")}</button>
          </div>
        )}
      </div>
      <Toast toast={toast} onDone={() => setToast(null)} />
    </SettingsShell>
  );
}
