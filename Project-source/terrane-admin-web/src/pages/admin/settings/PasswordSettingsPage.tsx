/** 设置 → 密码策略。最小长度 / 字符类别数——前后台所有口令校验点统一生效。
 *  与 登录设置 共用 system_settings['security']（GET/PATCH /settings/security 全量），本页只编辑密码子集。 */

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { useAuth } from "@/auth/AuthContext";
import { NumberStepper } from "@/components/NumberStepper";
import { Select } from "@/components/Select";
import { updateSecurity, useSecurity } from "@/lib/settings";
import { SettingsShell, Toast, toErrText, type ToastMsg } from "@/pages/admin/settings/_shared";

export function PasswordSettingsPage() {
  const { t } = useTranslation();
  const { has } = useAuth();
  const qc = useQueryClient();
  const query = useSecurity();
  const canWrite = has("system.settings.write");
  const ro = !canWrite;

  const [toast, setToast] = useState<ToastMsg | null>(null);
  const [busy, setBusy] = useState(false);
  const [minLength, setMinLength] = useState(12);
  const [charClasses, setCharClasses] = useState(3);

  const [hydrated, setHydrated] = useState(false);
  useEffect(() => {
    const s = query.data;
    if (!s || hydrated) return;
    setMinLength(s.password_min_length);
    setCharClasses(s.password_require_char_classes);
    setHydrated(true);
  }, [query.data, hydrated]);

  async function onSave() {
    if (!query.data) return;
    setBusy(true);
    try {
      // 全量提交：保留登录/会话子集不变，只改密码子集。
      await updateSecurity({
        ...query.data,
        password_min_length: minLength,
        password_require_char_classes: charClasses,
      });
      await qc.invalidateQueries({ queryKey: ["settings", "security"] });
      setToast({ kind: "success", text: t("settings.savedSecurity") });
    } catch (e) { setToast({ kind: "error", text: toErrText(e, t) }); }
    finally { setBusy(false); }
  }

  const lenValid = minLength >= 8 && minLength <= 128;

  return (
    <SettingsShell title={t("settings.password.title")} desc={t("settings.password.desc")}>
      <section className="rounded-xl border border-border/70 bg-surface/40 p-5">
        <div className="grid grid-cols-2 gap-4">
          <label className="text-sm font-medium text-ink">{t("settings.security.minLength")}
            <NumberStepper className="mt-1.5" value={minLength} onChange={setMinLength}
              min={8} max={128} disabled={ro || busy} />
            <span className="mt-1 block text-xs font-normal text-ink-faint">{t("settings.security.minLengthHint")}</span>
          </label>
          <label className="text-sm font-medium text-ink">{t("settings.security.charClasses")}
            <Select className="mt-1.5" value={String(charClasses)} onChange={(v) => setCharClasses(Number(v))}
              disabled={ro || busy} ariaLabel={t("settings.security.charClasses")}
              options={[1, 2, 3, 4].map((n) => ({ value: String(n), label: t("settings.security.charClassesN", { n }) }))} />
            <span className="mt-1 block text-xs font-normal text-ink-faint">{t("settings.security.charClassesHint")}</span>
          </label>
        </div>

        {canWrite && (
          <div className="mt-4 flex items-center">
            <span className="flex-1" />
            <button type="button" onClick={onSave} disabled={busy || !lenValid || !hydrated}
              className="rounded-(--radius-control) bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-50">
              {busy ? t("common.saving") : t("common.save")}</button>
          </div>
        )}
      </section>
      <Toast toast={toast} onDone={() => setToast(null)} />
    </SettingsShell>
  );
}
