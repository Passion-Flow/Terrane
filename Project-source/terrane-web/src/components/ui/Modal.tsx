/** 居中弹窗组件 —— 全前台统一。backdrop/Esc 关闭,header/body/footer。 */

import { X } from "@phosphor-icons/react";
import { useEffect, type ReactNode } from "react";

interface Props {
  open: boolean;
  onClose: () => void;
  title?: ReactNode;
  desc?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  size?: "sm" | "md" | "lg";
}

const W = { sm: "max-w-sm", md: "max-w-md", lg: "max-w-lg" };

export function Modal({ open, onClose, title, desc, children, footer, size = "md" }: Props) {
  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", h);
    return () => document.removeEventListener("keydown", h);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4 backdrop-blur-[2px]" onClick={onClose}>
      <div role="dialog" aria-modal="true"
        className={`w-full ${W[size]} animate-[modalIn_.15s_ease-out] rounded-(--radius-card) border border-border bg-surface shadow-2xl`}
        onClick={(e) => e.stopPropagation()}>
        {(title || desc) && (
          <div className="flex items-start justify-between gap-3 border-b border-border/60 px-6 py-4">
            <div>
              {title && <h2 className="text-base font-semibold text-ink">{title}</h2>}
              {desc && <p className="mt-1 text-[13px] text-ink-secondary">{desc}</p>}
            </div>
            <button type="button" onClick={onClose} className="-me-1.5 -mt-1 rounded-lg p-1.5 text-ink-faint transition hover:bg-canvas hover:text-ink">
              <X className="size-4.5" />
            </button>
          </div>
        )}
        <div className="px-6 py-5">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t border-border/60 px-6 py-3.5">{footer}</div>}
      </div>
    </div>
  );
}
