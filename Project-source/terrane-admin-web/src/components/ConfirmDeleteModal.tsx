/** Type-to-confirm delete modal (GitHub-style misclick guard) —— all deletions across the project go through here:
 *  the user must **type the exact target identifier (name/email)** into the field; only an exact match with target enables the "Delete" button.
 *  Convention: every irreversible delete action uses this component instead of a plain confirmation dialog. */

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
  /** Target identifier (name/email) the user must type verbatim; only an exact match is allowed through. */
  target: string;
  onConfirm: () => void;
  busy?: boolean;
  error?: string;
  /** Label for the delete button; defaults to common.delete. */
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
