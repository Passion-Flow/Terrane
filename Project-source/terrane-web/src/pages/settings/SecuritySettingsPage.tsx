/** Security settings —— change password + two-factor authentication (2FA). */
import { Key } from "@phosphor-icons/react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router";
import { TwofaCard } from "@/components/TwofaCard";
import { PageHeader } from "@/components/ui/PageHeader";
import { FALLBACK_LANG, isSupported } from "@/i18n/langs";

export function SecuritySettingsPage() {
  const { t } = useTranslation();
  const { lang } = useParams();
  const seg = lang && isSupported(lang) ? lang : FALLBACK_LANG;
  return (
    <div className="px-8 py-10"><div className="mx-auto max-w-2xl">
      <PageHeader title={t("nav.security")} subtitle={t("securitySettings.subtitle")} back />
      <div className="mt-6 rounded-(--radius-card) border border-border/70 bg-surface/40 p-5">
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-2 text-sm text-ink"><Key className="size-4.5 text-ink-faint" /> {t("account.password")}</span>
          <Link to={`/${seg}/forgot-password`} className="rounded-(--radius-control) border border-border px-3 py-1.5 text-[13px] text-ink-secondary transition hover:bg-canvas hover:text-ink">{t("account.changePassword")}</Link>
        </div>
      </div>
      <TwofaCard />
    </div></div>
  );
}
