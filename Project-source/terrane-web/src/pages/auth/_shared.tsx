/** Shared scaffold for frontend auth pages — top bar (Logo + language/theme) + centered narrow column + top-right toast. */

import { CheckCircle, XCircle } from "@phosphor-icons/react";
import { useEffect, useState, type ReactNode } from "react";

import { LanguageSelect } from "@/components/LanguageSelect";
import { Logo } from "@/components/Logo";
import { ThemeToggle } from "@/components/ThemeToggle";
import { ApiError } from "@/lib/api";

export const fieldClass =
  "w-full rounded-(--radius-control) border border-border bg-canvas px-3.5 py-2.5 text-sm text-ink outline-none transition placeholder:text-ink-faint focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/40 disabled:opacity-50";

export function errorKey(err: unknown): string {
  const code = err instanceof ApiError ? err.code : "SYSTEM_HTTP_ERROR";
  return `errors.${code}`;
}

export interface ToastMsg {
  kind: "error" | "success";
  text: string;
}

export function useToast(): [ToastMsg | null, (m: ToastMsg | null) => void] {
  return useState<ToastMsg | null>(null);
}

export function Toast({ toast, onDone }: { toast: ToastMsg | null; onDone: () => void }) {
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

export function AuthShell({ children }: { children: ReactNode }) {
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
        <div className="w-full max-w-[400px]">{children}</div>
      </main>
    </div>
  );
}
