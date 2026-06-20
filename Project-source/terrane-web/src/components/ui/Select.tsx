/** 统一下拉组件（自建,非原生 select)—— 全前台所有下拉都用它。
 *  popover + 键盘导航 + 点击外部关闭 + 单一 accent + 选中态。 */

import { Check, CaretUpDown } from "@phosphor-icons/react";
import { useEffect, useId, useRef, useState } from "react";

export interface SelectOption<T extends string = string> {
  value: T;
  label: string;
  hint?: string;
  icon?: React.ReactNode;
}

interface Props<T extends string> {
  value: T;
  options: SelectOption<T>[];
  onChange: (v: T) => void;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
  size?: "sm" | "md";
}

export function Select<T extends string>({
  value, options, onChange, placeholder = "选择…", disabled, className = "", size = "md",
}: Props<T>) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const ref = useRef<HTMLDivElement>(null);
  const id = useId();
  const current = options.find((o) => o.value === value);

  useEffect(() => {
    if (!open) return;
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, [open]);

  useEffect(() => {
    if (open) setActive(Math.max(0, options.findIndex((o) => o.value === value)));
  }, [open, value, options]);

  function onKey(e: React.KeyboardEvent) {
    if (disabled) return;
    if (!open && (e.key === "Enter" || e.key === "ArrowDown" || e.key === " ")) { e.preventDefault(); setOpen(true); return; }
    if (!open) return;
    if (e.key === "Escape") { setOpen(false); return; }
    if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, options.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
    else if (e.key === "Enter") { e.preventDefault(); const o = options[active]; if (o) { onChange(o.value); setOpen(false); } }
  }

  const pad = size === "sm" ? "px-2.5 py-1.5 text-[13px]" : "px-3 py-2 text-sm";

  return (
    <div ref={ref} className={`relative ${className}`}>
      <button type="button" disabled={disabled} aria-haspopup="listbox" aria-expanded={open} aria-controls={id}
        onClick={() => !disabled && setOpen((v) => !v)} onKeyDown={onKey}
        className={`flex w-full items-center justify-between gap-2 rounded-(--radius-control) border border-border bg-canvas ${pad} text-ink outline-none transition focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/30 disabled:opacity-50 ${open ? "border-accent ring-2 ring-accent/30" : "hover:border-ink-faint/50"}`}>
        <span className={`flex min-w-0 items-center gap-1.5 ${current ? "text-ink" : "text-ink-faint"}`}>
          {current?.icon}<span className="truncate">{current?.label ?? placeholder}</span>
        </span>
        <CaretUpDown className="size-4 shrink-0 text-ink-faint" />
      </button>
      {open && (
        <ul id={id} role="listbox" tabIndex={-1}
          className="absolute z-50 mt-1.5 max-h-64 w-full overflow-auto rounded-(--radius-control) border border-border bg-surface p-1 shadow-lg">
          {options.length === 0 && <li className="px-2.5 py-2 text-[13px] text-ink-faint">无可选项</li>}
          {options.map((o, i) => (
            <li key={o.value} role="option" aria-selected={o.value === value}
              onMouseEnter={() => setActive(i)}
              onClick={() => { onChange(o.value); setOpen(false); }}
              className={`flex cursor-pointer items-center justify-between gap-2 rounded-[6px] px-2.5 py-1.5 text-[13px] transition ${
                i === active ? "bg-canvas text-ink" : "text-ink-secondary"}`}>
              <span className="flex min-w-0 items-center gap-1.5">
                {o.icon}
                <span className="truncate">{o.label}</span>
                {o.hint && <span className="truncate text-xs text-ink-faint">{o.hint}</span>}
              </span>
              {o.value === value && <Check className="size-4 shrink-0 text-accent" weight="bold" />}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
