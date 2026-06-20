/** 通用下拉选择器 —— 自定义组件（非原生 select），视觉与表单输入一致。
 *  button 触发 + 点击外部关闭 + 绝对定位面板 + 选中打勾。受控：value/onChange。 */

import { CaretDown, Check } from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";

export interface SelectOption {
  value: string;
  label: string;
}

interface SelectProps {
  value: string;
  onChange: (value: string) => void;
  options: SelectOption[];
  placeholder?: string;
  disabled?: boolean;
  ariaLabel?: string;
  className?: string;
}

const TRIGGER =
  "flex w-full items-center gap-2 rounded-(--radius-control) border border-border bg-canvas px-3.5 py-2.5 text-sm text-ink outline-none transition focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/40 disabled:opacity-50";

export function Select({ value, onChange, options, placeholder, disabled, ariaLabel, className }: SelectProps) {
  const [open, setOpen] = useState(false);
  const [dropUp, setDropUp] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  const selected = options.find((o) => o.value === value);

  function toggle() {
    if (!open && ref.current) {
      // 触发器在视口下半部 → 向上展开，避免下拉超出弹窗/视口底部。
      setDropUp(ref.current.getBoundingClientRect().bottom > window.innerHeight * 0.6);
    }
    setOpen((v) => !v);
  }

  function pick(next: string) {
    setOpen(false);
    if (next !== value) onChange(next);
  }

  return (
    <div ref={ref} className={`relative ${className ?? ""}`}>
      <button
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={ariaLabel}
        disabled={disabled}
        onClick={toggle}
        className={TRIGGER}
      >
        <span className={`flex-1 truncate text-start ${selected ? "text-ink" : "text-ink-faint"}`}>
          {selected ? selected.label : placeholder ?? ""}
        </span>
        <CaretDown size={14} className={`shrink-0 text-ink-faint transition ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div
          role="listbox"
          className={`absolute inset-x-0 z-50 max-h-60 overflow-auto rounded-(--radius-control) border border-border bg-surface py-1 shadow-lg ${
            dropUp ? "bottom-full mb-1.5" : "mt-1.5"}`}
        >
          {options.map((o) => (
            <button
              key={o.value}
              type="button"
              role="option"
              aria-selected={o.value === value}
              onClick={() => pick(o.value)}
              className="flex w-full items-center gap-2.5 px-3.5 py-2 text-sm text-ink hover:bg-canvas"
            >
              <span className="flex-1 truncate text-start">{o.label}</span>
              {o.value === value && <Check size={15} className="shrink-0 text-accent" />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
