/** 输入确认删除模态（GitHub 式防误删）——全项目删除统一走这里:
 *  必须在输入框**精确键入目标标识(名称/邮箱)**,与 target 完全一致才能点「删除」。
 *  约定:任何不可撤销的删除动作都用本组件,不再用普通确认弹窗。 */

import { useEffect, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { Modal } from "@/components/Modal";

const FIELD = "w-full rounded-(--radius-control) border border-border bg-canvas px-3 py-2 text-sm text-ink outline-none transition focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/30";

export function ConfirmDeleteModal({
  open, onClose, title, desc, target, onConfirm, busy, error, confirmLabel,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  desc: ReactNode;
  /** 用户必须逐字键入的目标标识(名称/邮箱),完全一致才放行。 */
  target: string;
  onConfirm: () => void;
  busy?: boolean;
  error?: string;
  /** 删除按钮文案,默认 common.delete。 */
  confirmLabel?: string;
}) {
  const { t } = useTranslation();
  const [val, setVal] = useState("");
  useEffect(() => { if (open) setVal(""); }, [open, target]);

  const tgt = target.trim();
  const matches = tgt !== "" && val.trim() === tgt;

  return (
    <Modal open={open} onClose={onClose} title={title}
      footer={<>
        <button type="button" onClick={onClose}
          className="rounded-(--radius-control) px-3.5 py-1.5 text-[13px] text-ink-secondary hover:bg-canvas">{t("common.cancel")}</button>
        <button type="button" onClick={onConfirm} disabled={!matches || busy}
          className="rounded-(--radius-control) bg-danger px-3.5 py-1.5 text-[13px] font-medium text-white transition hover:opacity-90 disabled:opacity-50">
          {busy ? t("common.loading") : confirmLabel ?? t("common.delete")}</button>
      </>}>
      <p className="text-sm text-ink-secondary">{desc}</p>
      <p className="mt-3.5 text-[13px] text-ink-secondary">
        {t("common.confirmDeletePrompt")}
        <span className="ms-1 select-all break-all rounded bg-canvas px-1.5 py-0.5 font-mono text-[12px] text-ink">{target}</span>
      </p>
      <input value={val} onChange={(e) => setVal(e.target.value)} autoFocus autoComplete="off"
        spellCheck={false} placeholder={target} disabled={busy}
        onKeyDown={(e) => { if (e.key === "Enter" && matches && !busy) onConfirm(); }}
        className={`mt-1.5 ${FIELD}`} />
      {error && <p className="mt-3 text-[13px] text-danger">{error}</p>}
    </Modal>
  );
}
