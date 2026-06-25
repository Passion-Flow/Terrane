/** Knowledge base settings subpage —— manage sharing (add/remove members) + rename the base + delete the base (type-to-confirm). */

import { CircleNotch, Trash, UserPlus, X } from "@phosphor-icons/react";
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";

import { Modal } from "@/components/ui/Modal";
import { Select } from "@/components/ui/Select";
import { useKb } from "@/components/KbLayout";
import { ApiError } from "@/lib/api";
import {
  addMember, deleteKb, listMembers, removeMember, updateKb,
  type KbMember,
} from "@/lib/kb";

export function SettingsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { id, seg, kb, reload } = useKb();

  // share members
  const [owner, setOwner] = useState<KbMember | null>(null);
  const [members, setMembers] = useState<KbMember[]>([]);
  const [shareEmail, setShareEmail] = useState("");
  const [shareRole, setShareRole] = useState<"viewer" | "editor">("viewer");
  const [shareErr, setShareErr] = useState("");
  const [shareBusy, setShareBusy] = useState(false);

  // rename
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [savingName, setSavingName] = useState(false);
  const [nameSaved, setNameSaved] = useState(false);

  // delete kb (type-to-confirm)
  const [delKbOpen, setDelKbOpen] = useState(false);
  const [delKbInput, setDelKbInput] = useState("");

  const loadMembers = useCallback(async () => {
    try { const r = await listMembers(id); setOwner(r.owner); setMembers(r.members); } catch { /* ignore */ }
  }, [id]);
  useEffect(() => { void loadMembers(); }, [loadMembers]);
  useEffect(() => { if (kb) { setName(kb.name); setDesc(kb.description ?? ""); } }, [kb]);

  const isOwner = !!kb?.is_owner;

  async function onAddMember() {
    if (!shareEmail.trim() || shareBusy) return;
    setShareBusy(true); setShareErr("");
    try { await addMember(id, { email: shareEmail.trim(), role: shareRole }); setShareEmail(""); await loadMembers(); }
    catch (e) { setShareErr(e instanceof ApiError ? t(`errors.${e.code}`, { defaultValue: e.message }) : t("errors.SYSTEM_HTTP_ERROR")); }
    finally { setShareBusy(false); }
  }
  async function onRemoveMember(m: KbMember) {
    try { await removeMember(id, m.user_id); await loadMembers(); } catch { /* ignore */ }
  }

  async function onSaveName() {
    if (!name.trim() || savingName) return;
    setSavingName(true); setNameSaved(false);
    try { await updateKb(id, { name: name.trim(), description: desc }); await reload(); setNameSaved(true); }
    catch { /* ignore */ }
    finally { setSavingName(false); }
  }

  async function onDeleteKb() {
    if (!isOwner) return;
    try { await deleteKb(id); navigate(`/${seg}/kb`); } catch { /* ignore */ }
  }

  const field = "w-full rounded-(--radius-control) border border-border bg-canvas px-3 py-2 text-sm text-ink outline-none focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/30";

  return (
    <div className="px-6 py-8 sm:px-8">
      <div className="mx-auto max-w-3xl space-y-8">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-ink">{t("kbNav.settings")}</h1>
          <p className="mt-1 text-sm text-ink-secondary">{t("kbPages.settingsSubtitle")}</p>
        </div>

        {/* Basic info / rename */}
        <section className="rounded-(--radius-card) border border-border/70 bg-surface/40 p-5">
          <h2 className="text-sm font-semibold text-ink">{t("kbSettings.basics")}</h2>
          <div className="mt-4 space-y-3.5">
            <label className="block text-sm font-medium text-ink">{t("kb.fName")}
              <input value={name} onChange={(e) => { setName(e.target.value); setNameSaved(false); }} disabled={!isOwner || savingName} className={`mt-1.5 ${field}`} /></label>
            <label className="block text-sm font-medium text-ink">{t("kb.fDesc")}
              <textarea value={desc} onChange={(e) => { setDesc(e.target.value); setNameSaved(false); }} rows={2} disabled={!isOwner || savingName} className={`mt-1.5 ${field}`} /></label>
            {isOwner && (
              <div className="flex items-center gap-3">
                <button onClick={onSaveName} disabled={savingName || !name.trim()}
                  className="flex items-center gap-1.5 rounded-(--radius-control) bg-accent px-3.5 py-1.5 text-sm font-medium text-white transition hover:bg-accent-hover disabled:opacity-50">
                  {savingName ? <><CircleNotch className="size-4 animate-spin" /> {t("common.saving")}</> : t("common.save")}
                </button>
                {nameSaved && <span className="text-[13px] text-success">{t("kbSettings.saved")}</span>}
              </div>
            )}
          </div>
        </section>

        {/* Sharing */}
        {isOwner && (
          <section className="rounded-(--radius-card) border border-border/70 bg-surface/40 p-5">
            <h2 className="text-sm font-semibold text-ink">{t("kb.shareTitle")}</h2>
            <p className="mt-1 text-[13px] text-ink-secondary">{t("kb.shareDesc")}</p>
            <div className="mt-4 flex items-end gap-2">
              <label className="flex-1 text-sm font-medium text-ink">{t("kb.memberEmail")}
                <input value={shareEmail} onChange={(e) => setShareEmail(e.target.value)} placeholder="user@example.com" disabled={shareBusy} className={`mt-1.5 ${field}`} /></label>
              <Select className="w-28" value={shareRole} onChange={(v) => setShareRole(v as "viewer" | "editor")} disabled={shareBusy}
                options={[{ value: "viewer", label: t("kb.role.viewer") }, { value: "editor", label: t("kb.role.editor") }]} />
              <button onClick={onAddMember} disabled={shareBusy || !shareEmail.trim()}
                className="flex items-center gap-1 rounded-(--radius-control) bg-accent px-3 py-2 text-sm font-medium text-white transition hover:bg-accent-hover disabled:opacity-50">
                <UserPlus className="size-4" />
              </button>
            </div>
            {shareErr && <p className="mt-2 text-[13px] text-danger">{shareErr}</p>}
            <div className="mt-4 space-y-1.5">
              {owner && (
                <div className="flex items-center justify-between rounded-(--radius-control) bg-canvas px-3 py-2 text-[13px]">
                  <span className="text-ink">{owner.username ?? owner.email}</span>
                  <span className="text-xs text-ink-faint">{t("kb.role.owner")}</span>
                </div>
              )}
              {members.map((m) => (
                <div key={m.user_id} className="group/m flex items-center justify-between rounded-(--radius-control) border border-border/50 px-3 py-2 text-[13px]">
                  <span className="text-ink">{m.username ?? m.email}</span>
                  <span className="flex items-center gap-2">
                    <span className="text-xs text-ink-faint">{t(`kb.role.${m.role}`)}</span>
                    <button onClick={() => onRemoveMember(m)} className="rounded p-0.5 text-ink-faint opacity-0 transition hover:text-danger group-hover/m:opacity-100"><X className="size-3.5" /></button>
                  </span>
                </div>
              ))}
              {members.length === 0 && <p className="py-2 text-center text-xs text-ink-faint">{t("kb.noMembers")}</p>}
            </div>
          </section>
        )}

        {/* Danger zone — delete base */}
        {isOwner && (
          <section className="rounded-(--radius-card) border border-danger/40 bg-danger-soft/30 p-5">
            <h2 className="text-sm font-semibold text-danger">{t("kbSettings.dangerZone")}</h2>
            <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
              <p className="text-[13px] text-ink-secondary">{t("kbSettings.deleteHint")}</p>
              <button onClick={() => { setDelKbOpen(true); setDelKbInput(""); }}
                className="flex shrink-0 items-center gap-1.5 rounded-(--radius-control) border border-danger/40 px-3 py-1.5 text-sm font-medium text-danger transition hover:bg-danger-soft">
                <Trash className="size-4" /> {t("kb.deleteKb")}
              </button>
            </div>
          </section>
        )}
      </div>

      {/* Delete base — type-to-confirm */}
      <Modal open={delKbOpen} onClose={() => { setDelKbOpen(false); setDelKbInput(""); }} title={t("kb.deleteKb")}
        desc={kb ? t("kb.confirmDelete", { name: kb.name }) : ""}
        footer={
          <>
            <button onClick={() => { setDelKbOpen(false); setDelKbInput(""); }} className="rounded-(--radius-control) px-3.5 py-1.5 text-sm text-ink-secondary transition hover:bg-canvas">{t("common.cancel")}</button>
            <button onClick={onDeleteKb} disabled={delKbInput !== kb?.name}
              className="rounded-(--radius-control) bg-danger px-3.5 py-1.5 text-sm font-medium text-white transition hover:opacity-90 disabled:opacity-40">{t("common.delete")}</button>
          </>
        }>
        <label className="block text-[13px] text-ink-secondary">{kb && t("kb.typeToConfirm", { name: kb.name })}
          <input value={delKbInput} onChange={(e) => setDelKbInput(e.target.value)} autoFocus className={`mt-1.5 ${field}`} /></label>
      </Modal>
    </div>
  );
}
