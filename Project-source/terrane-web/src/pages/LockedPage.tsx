/** Frontend locked page (modeled on Dify's frontend signin locked state): polls License status, showing
 *  the locked copy character-by-character when not activated + a description that varies by verdict +
 *  guidance to activate in the admin console (the frontend has no activation rights; activation lives only in admin-web).
 *  Once activated (unlocked), automatically proceeds into the app (delivered in stage ②; for now a placeholder welcome). */

import { useQuery } from "@tanstack/react-query";
import { SealCheck } from "@phosphor-icons/react";
import { useTranslation } from "react-i18next";

import { LanguageSelect } from "@/components/LanguageSelect";
import { Logo } from "@/components/Logo";
import { ThemeToggle } from "@/components/ThemeToggle";
import { ApiError } from "@/lib/api";
import { getLicenseStatus, type LicenseStatus } from "@/lib/license";

function lockedDescKey(status: LicenseStatus["status"]): string {
  if (status === "expired") return "locked.expiredDesc";
  if (status === "revoked") return "locked.revokedDesc";
  if (status === "binding_mismatch") return "locked.mismatchDesc";
  return "locked.desc";
}

function errorKey(err: unknown): string {
  const code = err instanceof ApiError ? err.code : "SYSTEM_HTTP_ERROR";
  return `errors.${code}`;
}

export function LockedPage() {
  const { t } = useTranslation();
  const { data: status, error } = useQuery({
    queryKey: ["license-status"],
    queryFn: getLicenseStatus,
    // Poll fast (3s) while locked so this page enters near-instantly once the admin activates; fall back to 8s once unlocked.
    refetchInterval: (query) => (query.state.data?.unlocked ? 8_000 : 3_000),
  });

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
        {status && !status.unlocked ? (
          <div className="w-full max-w-sm rounded-xl border border-border/70 bg-surface p-5 shadow-sm">
            <div className="relative mb-4 inline-block">
              <span className="flex size-10 items-center justify-center rounded-lg border border-border/70 bg-canvas">
                <SealCheck size={20} className="text-ink" />
              </span>
              <span className="absolute -end-1 -top-1 flex size-4 items-center justify-center rounded-full bg-warning text-[10px] font-bold text-white">
                !
              </span>
            </div>
            <h2 className="mb-1.5 text-[15px] font-semibold text-ink">{t("locked.message")}</h2>
            <p className="text-[13px] leading-relaxed text-ink-secondary">{t(lockedDescKey(status.status))}</p>
          </div>
        ) : status?.unlocked ? (
          // Activated: the business frontend ships in stage ②; placeholder welcome here.
          <div className="w-full max-w-sm rounded-xl border border-border/70 bg-surface p-6 text-center shadow-sm">
            <div className="mb-3 flex justify-center">
              <Logo />
            </div>
            <p className="text-[13px] text-ink-secondary">Activated · The knowledge workspace will be available in a later stage</p>
          </div>
        ) : error != null ? (
          <p role="alert" className="text-sm text-danger">
            {t(errorKey(error))}
          </p>
        ) : null}
      </main>
    </div>
  );
}
