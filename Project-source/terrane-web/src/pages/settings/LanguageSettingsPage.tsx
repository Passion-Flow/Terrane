/** Language settings. */
import { useTranslation } from "react-i18next";
import { useNavigate, useParams, useLocation } from "react-router";
import { PageHeader } from "@/components/ui/PageHeader";
import { Select } from "@/components/ui/Select";
import { applyLang } from "@/i18n";
import { FALLBACK_LANG, SUPPORTED_LANGS, isSupported } from "@/i18n/langs";

const L: Record<string, string> = { "zh-CN": "简体中文", en: "English (United States)" };
export function LanguageSettingsPage() {
  const { t } = useTranslation();
  const { lang } = useParams(); const navigate = useNavigate(); const loc = useLocation();
  const seg = lang && isSupported(lang) ? lang : FALLBACK_LANG;
  return (
    <div className="px-8 py-10"><div className="mx-auto max-w-2xl">
      <PageHeader title={t("nav.language")} subtitle={t("langSettings.subtitle")} back />
      <div className="mt-6 rounded-(--radius-card) border border-border/70 bg-surface/40 p-5">
        <label className="block text-sm font-medium text-ink">{t("langSettings.label")}</label>
        <Select className="mt-2 w-64" value={seg} options={SUPPORTED_LANGS.map((l) => ({ value: l, label: L[l] ?? l }))}
          onChange={(v) => { applyLang(v); navigate(loc.pathname.replace(/^\/[^/]+/, `/${v}`)); }} />
      </div>
    </div></div>
  );
}
