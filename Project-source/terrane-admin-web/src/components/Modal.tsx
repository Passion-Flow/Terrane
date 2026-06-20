/** 通用模态框 —— 居中卡片 + 遮罩，点击遮罩/Esc 关闭。紧凑精致。 */

import { X } from "@phosphor-icons/react";
import { useEffect, type ReactNode } from "react";

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  /** 底部操作区（按钮）。 */
  footer?: ReactNode;
}

export function Modal({ open, onClose, title, children, footer }: ModalProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <button type="button" aria-label="close" onClick={onClose} className="absolute inset-0 bg-ink/40" />
      <div className="relative z-10 w-full max-w-md rounded-xl border border-border bg-surface shadow-xl">
        <div className="flex items-center justify-between border-b border-border/70 px-5 py-3.5">
          <h2 className="text-base font-semibold text-ink">{title}</h2>
          <button type="button" onClick={onClose}
            className="flex size-7 items-center justify-center rounded-(--radius-control) text-ink-faint transition hover:bg-canvas hover:text-ink">
            <X className="size-4" />
          </button>
        </div>
        <div className="px-5 py-4">{children}</div>
        {footer && <div className="flex items-center justify-end gap-2 border-t border-border/70 px-5 py-3.5">{footer}</div>}
      </div>
    </div>
  );
}
