/** Theme toggle — three states: light/dark/follow system (icon dropdown, checkmark on the selected one). */

import { Check, Desktop, Moon, Sun } from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { applyTheme, storedTheme, THEMES, type Theme } from "@/lib/theme";

const ICONS: Record<Theme, typeof Sun> = { light: Sun, dark: Moon, system: Desktop };

export function ThemeToggle() {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [theme, setTheme] = useState<Theme>(storedTheme);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  const pick = (next: Theme) => {
    setTheme(next);
    applyTheme(next);
    setOpen(false);
  };
  const Current = ICONS[theme];

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        aria-label={t("theme.label")}
        onClick={() => setOpen((v) => !v)}
        className="flex size-8 items-center justify-center rounded-(--radius-control) text-ink-secondary hover:bg-surface hover:text-ink focus-visible:ring-2 focus-visible:ring-accent"
      >
        <Current size={17} />
      </button>
      {open && (
        <div className="absolute end-0 z-50 mt-1.5 min-w-36 rounded-(--radius-control) border border-border bg-surface py-1 shadow-lg">
          {THEMES.map((mode) => {
            const Icon = ICONS[mode];
            return (
              <button
                key={mode}
                type="button"
                onClick={() => pick(mode)}
                className="flex w-full items-center gap-2.5 px-3 py-2 text-sm text-ink hover:bg-canvas"
              >
                <Icon size={16} className="text-ink-secondary" />
                <span className="flex-1 text-start">{t(`theme.${mode}`)}</span>
                {theme === mode && <Check size={15} className="text-accent" />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
