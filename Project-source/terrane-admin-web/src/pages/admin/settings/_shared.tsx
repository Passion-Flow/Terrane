/** Shared pieces for the settings sub-pages — Toast / Card / input field styles / error-code translation.
 *  Settings is split into independent sub-pages (Email / Branding …) and keeps growing over time; common pieces live here to avoid duplication. */

import { CheckCircle, XCircle } from "@phosphor-icons/react";
import { useEffect } from "react";
import type { TFunction } from "i18next";

import { ApiError } from "@/lib/api";

export interface ToastMsg { kind: "error" | "success"; text: string }

export function Toast({ toast, onDone }: { toast: ToastMsg | null; onDone: () => void }) {
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(onDone, 4000);
    return () => clearTimeout(timer);
  }, [toast, onDone]);
  if (!toast) return null;
  const error = toast.kind === "error";
  return (
    <div role="alert"
      className={`fixed end-6 top-6 z-50 flex max-w-sm items-center gap-2 rounded-(--radius-control) px-4 py-3 text-sm shadow-lg ${
        error ? "bg-danger-soft text-danger" : "bg-accent-soft text-accent"}`}>
      {error ? <XCircle className="size-4 shrink-0" weight="fill" />
             : <CheckCircle className="size-4 shrink-0" weight="fill" />}
      {toast.text}
    </div>
  );
}

export const field = "w-full rounded-(--radius-control) border border-border bg-canvas px-3.5 py-2.5 text-sm text-ink outline-none transition placeholder:text-ink-faint focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/40 disabled:opacity-50";

/** Sub-page shell: title + description + content. Every settings sub-page uses the same narrow, centered column. */
export function SettingsShell({ title, desc, children }: {
  title: string; desc: string; children: React.ReactNode;
}) {
  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-xl font-semibold tracking-tight text-ink">{title}</h1>
      <p className="mt-1 text-[13px] text-ink-secondary">{desc}</p>
      <div className="mt-5">{children}</div>
    </div>
  );
}

/** API error → message text (for email errors with a hint, prefer the precise hint message). */
export function toErrText(e: unknown, t: TFunction): string {
  if (e instanceof ApiError) {
    const hint = (e.details as { hint?: string } | undefined)?.hint;
    if (hint) return t(`wizard.emailHint.${hint}`, { defaultValue: t(`errors.${e.code}`) });
    return t(`errors.${e.code}`);
  }
  return t("errors.SYSTEM_HTTP_ERROR");
}
