/** 数字步进器 —— 平时是干净的输入框（无原生 spin 箭头）；鼠标悬停 / 聚焦时右侧淡入 −/+ 微调。
 *  范围 clamp 到 [min,max]；可直接键入也可点按。通用件,各设置页复用。 */

import { Minus, Plus } from "@phosphor-icons/react";

export function NumberStepper({
  value, onChange, min = 0, max = 9999, step = 1, disabled, className,
}: {
  value: number;
  onChange: (n: number) => void;
  min?: number;
  max?: number;
  step?: number;
  disabled?: boolean;
  className?: string;
}) {
  const clamp = (n: number) => Math.max(min, Math.min(max, n));
  const set = (n: number) => { if (!Number.isNaN(n)) onChange(clamp(n)); };

  const input = "w-full rounded-(--radius-control) border border-border bg-canvas py-2.5 pe-16 ps-3.5 text-sm text-ink outline-none transition placeholder:text-ink-faint focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/40 disabled:opacity-50 [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none";
  const btn = "pointer-events-auto flex size-6 items-center justify-center rounded text-ink-secondary transition-colors hover:bg-surface hover:text-ink disabled:pointer-events-none disabled:opacity-30";

  return (
    <div className={`group relative ${className ?? ""}`}>
      <input type="number" value={value} min={min} max={max} disabled={disabled}
        onChange={(e) => set(Number(e.target.value))} className={input} />
      <div className="pointer-events-none absolute inset-y-0 end-1.5 flex items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
        <button type="button" tabIndex={-1} aria-label="decrement" disabled={disabled || value <= min}
          onClick={() => set(value - step)} className={btn}><Minus className="size-3.5" /></button>
        <button type="button" tabIndex={-1} aria-label="increment" disabled={disabled || value >= max}
          onClick={() => set(value + step)} className={btn}><Plus className="size-3.5" /></button>
      </div>
    </div>
  );
}
