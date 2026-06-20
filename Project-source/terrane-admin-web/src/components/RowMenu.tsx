/** 行操作菜单 —— 「⋯」按钮 + 下拉项列表。点击外部关闭，靠下时向上展开，右对齐。 */

import { DotsThree, type Icon } from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";

export interface RowMenuItem {
  label: string;
  icon: Icon;
  onClick: () => void;
  danger?: boolean;
}

export function RowMenu({ items, ariaLabel }: { items: RowMenuItem[]; ariaLabel: string }) {
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

  function toggle() {
    if (!open && ref.current) {
      setDropUp(ref.current.getBoundingClientRect().bottom > window.innerHeight * 0.6);
    }
    setOpen((v) => !v);
  }

  return (
    <div ref={ref} className="relative flex justify-end">
      <button type="button" onClick={toggle} aria-label={ariaLabel} aria-haspopup="menu"
        className="flex size-7 items-center justify-center rounded-(--radius-control) text-ink-faint transition hover:bg-canvas hover:text-ink">
        <DotsThree className="size-5" weight="bold" />
      </button>
      {open && (
        <div role="menu"
          className={`absolute end-0 z-50 min-w-40 rounded-(--radius-control) border border-border bg-surface py-1 shadow-lg ${
            dropUp ? "bottom-full mb-1" : "mt-1"}`}>
          {items.map((it) => (
            <button key={it.label} type="button" role="menuitem"
              onClick={() => { setOpen(false); it.onClick(); }}
              className={`flex w-full items-center gap-2.5 px-3 py-2 text-[13px] transition hover:bg-canvas ${
                it.danger ? "text-danger hover:text-danger" : "text-ink-secondary hover:text-ink"}`}>
              <it.icon className="size-4 shrink-0" />
              {it.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
