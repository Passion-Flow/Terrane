/** Email verification — entered via the ?token= link from the email; auto-verifies and shows the result. On success → go to login. */

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams, useSearchParams } from "react-router";

import { FALLBACK_LANG, isSupported } from "@/i18n/langs";
import { verifyEmail } from "@/lib/auth";
import { AuthShell } from "@/pages/auth/_shared";

export function VerifyEmailPage() {
  const { t } = useTranslation();
  const { lang } = useParams();
  const [params] = useSearchParams();
  const seg = lang && isSupported(lang) ? lang : FALLBACK_LANG;
  const token = params.get("token") ?? "";

  const [state, setState] = useState<"pending" | "ok" | "error">("pending");
  const ran = useRef(false);

  useEffect(() => {
    if (ran.current) return;
    ran.current = true;
    if (token === "") {
      setState("error");
      return;
    }
    verifyEmail(token).then(() => setState("ok")).catch(() => setState("error"));
  }, [token]);

  return (
    <AuthShell>
      <h1 className="text-[28px] font-bold leading-tight tracking-tight text-ink">{t("verify.title")}</h1>
      <p className="mt-3 text-sm text-ink-secondary">
        {state === "pending" ? t("verify.checking") : state === "ok" ? t("verify.ok") : t("verify.error")}
      </p>
      {state !== "pending" && (
        <Link to={`/${seg}/login`}
          className="mt-8 block w-full rounded-(--radius-control) bg-accent px-4 py-2.5 text-center text-sm font-medium text-white hover:bg-accent-hover">
          {t("register.toLogin")}
        </Link>
      )}
    </AuthShell>
  );
}
