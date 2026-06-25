/** Account settings — profile + change-password entry point. */

import { Envelope, Key, UserCircle } from "@phosphor-icons/react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router";

import { useAuth } from "@/auth/AuthContext";
import { TwofaCard } from "@/components/TwofaCard";
import { FALLBACK_LANG, isSupported } from "@/i18n/langs";

export function AccountPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { lang } = useParams();
  const seg = lang && isSupported(lang) ? lang : FALLBACK_LANG;

  const Row = ({ icon: Icon, label, value }: { icon: typeof UserCircle; label: string; value: string }) => (
    <div className="flex items-center gap-3 border-b border-border/50 py-3.5 last:border-0">
      <Icon className="size-5 text-ink-faint" />
      <span className="w-28 text-sm text-ink-secondary">{label}</span>
      <span className="text-sm text-ink">{value}</span>
    </div>
  );

  return (
    <div className="px-8 py-10">
      <div className="mx-auto max-w-2xl">
        <h1 className="text-2xl font-bold tracking-tight text-ink">{t("account.title")}</h1>
        <p className="mt-1.5 text-sm text-ink-secondary">{t("account.subtitle")}</p>

        <div className="mt-6 rounded-xl border border-border/70 bg-surface/40 px-5 py-2">
          <Row icon={UserCircle} label={t("account.username")} value={user?.username ?? "—"} />
          <Row icon={Envelope} label={t("account.email")} value={user?.email ?? "—"} />
        </div>

        <div className="mt-5 rounded-xl border border-border/70 bg-surface/40 p-5">
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-2 text-sm text-ink"><Key className="size-4.5 text-ink-faint" /> {t("account.password")}</span>
            <Link to={`/${seg}/forgot-password`} className="rounded-(--radius-control) border border-border px-3 py-1.5 text-[13px] text-ink-secondary transition hover:bg-canvas hover:text-ink">
              {t("account.changePassword")}
            </Link>
          </div>
        </div>

        <TwofaCard />
      </div>
    </div>
  );
}
