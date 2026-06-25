/** Centered profile edit modal — change avatar (any image format, scaled to a 256px jpeg via canvas) + rename. */

import { Camera, Trash } from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { useAuth } from "@/auth/AuthContext";
import { Avatar } from "@/components/ui/Avatar";
import { Modal } from "@/components/ui/Modal";
import { updateProfile } from "@/lib/auth";

/** Any image → center-cropped 256px square jpeg dataURL (supports png/jpg/webp/gif…). */
function resizeImage(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      const S = 256;
      const cv = document.createElement("canvas");
      cv.width = S; cv.height = S;
      const ctx = cv.getContext("2d");
      if (!ctx) { reject(new Error("no ctx")); return; }
      const scale = Math.max(S / img.width, S / img.height);
      const w = img.width * scale, h = img.height * scale;
      ctx.drawImage(img, (S - w) / 2, (S - h) / 2, w, h);
      URL.revokeObjectURL(url);
      resolve(cv.toDataURL("image/jpeg", 0.85));
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("bad image")); };
    img.src = url;
  });
}

export function ProfileModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const { user, refresh } = useAuth();
  const [name, setName] = useState(user?.username ?? "");
  const [avatar, setAvatar] = useState<string | null | undefined>(user?.avatar);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) { setName(user?.username ?? ""); setAvatar(user?.avatar ?? null); setErr(""); }
  }, [open, user]);

  async function onPick(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0]; e.target.value = "";
    if (!f) return;
    if (!f.type.startsWith("image/")) { setErr(t("profile.notImage")); return; }
    try { setAvatar(await resizeImage(f)); setErr(""); } catch { setErr(t("profile.imageFailed")); }
  }

  async function save() {
    if (busy) return;
    setBusy(true); setErr("");
    try {
      await updateProfile({ username: name.trim() || undefined, avatar: avatar ?? "" });
      await refresh();
      onClose();
    } catch { setErr(t("profile.saveFailed")); } finally { setBusy(false); }
  }

  const field = "w-full rounded-(--radius-control) border border-border bg-canvas px-3 py-2 text-sm text-ink outline-none focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/30";

  return (
    <Modal open={open} onClose={onClose} title={t("profile.title")} desc={t("profile.desc")}
      footer={<>
        <button type="button" onClick={onClose} className="rounded-(--radius-control) px-3.5 py-1.5 text-sm text-ink-secondary hover:bg-canvas">{t("common.cancel")}</button>
        <button type="button" onClick={save} disabled={busy} className="rounded-(--radius-control) bg-accent px-3.5 py-1.5 text-sm font-medium text-white transition active:translate-y-px hover:bg-accent-hover disabled:opacity-50">{busy ? t("common.saving") : t("common.save")}</button>
      </>}>
      <div className="flex items-center gap-4">
        <div className="relative">
          <Avatar src={avatar} name={name} email={user?.email} size={72} />
          <button type="button" onClick={() => fileRef.current?.click()}
            className="absolute -bottom-1 -end-1 flex size-7 items-center justify-center rounded-full border-2 border-surface bg-accent text-white shadow transition active:translate-y-px hover:bg-accent-hover">
            <Camera className="size-3.5" weight="fill" />
          </button>
          <input ref={fileRef} type="file" hidden accept="image/png,image/jpeg,image/webp,image/gif,image/*" onChange={onPick} />
        </div>
        <div className="flex-1">
          <p className="text-[13px] text-ink-secondary">{t("profile.avatarHint")}</p>
          {avatar && (
            <button type="button" onClick={() => setAvatar(null)} className="mt-1.5 flex items-center gap-1 text-xs text-danger hover:underline">
              <Trash className="size-3.5" /> {t("profile.removeAvatar")}
            </button>
          )}
        </div>
      </div>
      <label className="mt-5 block text-sm font-medium text-ink">{t("profile.name")}
        <input value={name} onChange={(e) => setName(e.target.value)} maxLength={64} disabled={busy} className={`mt-1.5 ${field}`} /></label>
      <div className="mt-3 text-[13px] text-ink-faint">{t("profile.email")}: {user?.email}</div>
      {err && <p className="mt-3 text-[13px] text-danger">{err}</p>}
    </Modal>
  );
}
