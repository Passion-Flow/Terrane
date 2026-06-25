/** Model channels —— platform-level LLM / embedding / rerank / web-search backends. Variant pattern: "New channel" -> type dropdown -> centered modal configuration.
 *  List + row ⋯ (edit / test connectivity / delete with type-to-confirm name). api_key is masked; the test performs a real /models probe. */

import { CaretDown, CheckCircle, PencilSimple, Plus, Pulse, Trash, XCircle } from "@phosphor-icons/react";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { useAuth } from "@/auth/AuthContext";
import { ConfirmDeleteModal } from "@/components/ConfirmDeleteModal";
import { Modal } from "@/components/Modal";
import { RowMenu, type RowMenuItem } from "@/components/RowMenu";
import { Select } from "@/components/Select";
import { ApiError } from "@/lib/api";
import {
  createChannel, deleteChannel, testChannel, updateChannel, useChannels, useProviders,
  type ChannelItem, type ChannelKind, type ProviderPreset,
} from "@/lib/channels";
import { StatusBadge } from "@/pages/admin/WorkspacesPage";

interface ToastMsg { kind: "error" | "success"; text: string }
function Toast({ toast, onDone }: { toast: ToastMsg | null; onDone: () => void }) {
  useEffect(() => { if (!toast) return; const t = setTimeout(onDone, 4000); return () => clearTimeout(t); }, [toast, onDone]);
  if (!toast) return null;
  const err = toast.kind === "error";
  return (
    <div role="alert" className={`fixed end-6 top-6 z-50 flex max-w-sm items-center gap-2 rounded-(--radius-control) px-4 py-3 text-sm shadow-lg ${err ? "bg-danger-soft text-danger" : "bg-accent-soft text-accent"}`}>
      {err ? <XCircle className="size-4 shrink-0" weight="fill" /> : <CheckCircle className="size-4 shrink-0" weight="fill" />}{toast.text}
    </div>
  );
}

const FIELD = "w-full rounded-(--radius-control) border border-border bg-canvas px-3 py-2 text-sm text-ink outline-none focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/30";
const KINDS: ChannelKind[] = ["chat", "embed", "rerank", "web_search", "vl", "asr", "tts"];

export function ChannelsPage() {
  const { t } = useTranslation();
  const { has } = useAuth();
  const qc = useQueryClient();
  const query = useChannels();
  const providers = useProviders().data?.providers ?? [];
  const rows = query.data?.items ?? [];
  const canWrite = has("platform.channel.write");

  const [toast, setToast] = useState<ToastMsg | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  // Create (variant): the selected provider preset -> open the modal
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const [createPreset, setCreatePreset] = useState<ProviderPreset | null>(null);
  // Edit
  const [editing, setEditing] = useState<ChannelItem | null>(null);
  // Form (shared between create + edit)
  const [name, setName] = useState("");
  const [kind, setKind] = useState<ChannelKind>("chat");
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  // Delete
  const [delT, setDelT] = useState<ChannelItem | null>(null);

  useEffect(() => {
    if (!menuOpen) return;
    const h = (e: MouseEvent) => { if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, [menuOpen]);

  const invalidate = () => qc.invalidateQueries({ queryKey: ["channels"] });
  function toErr(e: unknown) { setErr(e instanceof ApiError ? t(`errors.${e.code}`) : t("errors.SYSTEM_HTTP_ERROR")); }
  const presetFor = (p: ChannelProviderLike) => providers.find((x) => x.id === p);

  function openCreate(preset: ProviderPreset) {
    setMenuOpen(false); setCreatePreset(preset); setEditing(null);
    setName(""); setKind(preset.kind); setBaseUrl(preset.base_url); setModel(""); setApiKey(""); setErr("");
  }
  function openEdit(c: ChannelItem) {
    setEditing(c); setCreatePreset(null);
    setName(c.name); setKind(c.kind); setBaseUrl(c.base_url ?? ""); setModel(c.model ?? ""); setApiKey(""); setErr("");
  }

  const formProvider = createPreset ?? (editing ? presetFor(editing.provider) : null);
  const needsModel = formProvider?.needs_model ?? true;
  const modalOpen = !!createPreset || !!editing;

  async function onSave() {
    if (!name.trim() || busy) return;
    setBusy(true); setErr("");
    try {
      if (editing) {
        await updateChannel(editing.id, { name: name.trim(), kind, base_url: baseUrl, model, api_key: apiKey || undefined });
      } else if (createPreset) {
        await createChannel({ provider: createPreset.id, kind, name: name.trim(), base_url: baseUrl, model, api_key: apiKey || undefined });
      }
      invalidate(); setCreatePreset(null); setEditing(null);
      setToast({ kind: "success", text: t("common.save") });
    } catch (e) { toErr(e); } finally { setBusy(false); }
  }
  async function onTest(c: ChannelItem) {
    setToast({ kind: "success", text: t("channels.testing") });
    try {
      const r = await testChannel(c.id);
      if (r.data.ok) setToast({ kind: "success", text: t("channels.testOk") });
      else setToast({ kind: "error", text: t(`channels.testErr.${r.data.detail}`, { defaultValue: t("channels.testErr.failed") }) });
    } catch (e) { setToast({ kind: "error", text: e instanceof ApiError ? t(`errors.${e.code}`) : t("errors.SYSTEM_HTTP_ERROR") }); }
  }
  async function onDelete() {
    if (!delT || busy) return;
    setBusy(true); setErr("");
    try { await deleteChannel(delT.id); invalidate(); setDelT(null); }
    catch (e) { toErr(e); } finally { setBusy(false); }
  }

  function rowItems(c: ChannelItem): RowMenuItem[] {
    const items: RowMenuItem[] = [{ label: t("channels.test"), icon: Pulse, onClick: () => onTest(c) }];
    if (canWrite) {
      items.push({ label: t("members.edit"), icon: PencilSimple, onClick: () => openEdit(c) });
      items.push({ label: t("members.delete"), icon: Trash, danger: true, onClick: () => { setDelT(c); setErr(""); } });
    }
    return items;
  }

  const cell = "px-3.5 py-2 text-[13px]";
  const providerLabel = (p: string) => providers.find((x) => x.id === p)?.label ?? p;

  return (
    <div className="mx-auto max-w-5xl">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-ink">{t("channels.title")}</h1>
          <p className="mt-1 text-[13px] text-ink-secondary">{t("channels.desc")}</p>
        </div>
        {canWrite && (
          <div ref={menuRef} className="relative shrink-0">
            <button type="button" onClick={() => setMenuOpen((v) => !v)}
              className="flex items-center gap-1.5 rounded-full bg-accent px-3.5 py-1.5 text-[13px] font-medium text-white transition hover:bg-accent-hover">
              <Plus className="size-4" /> {t("channels.create")} <CaretDown className="size-3.5" />
            </button>
            {menuOpen && (
              <div className="absolute end-0 z-20 mt-1.5 w-56 overflow-hidden rounded-(--radius-control) border border-border bg-surface py-1 shadow-lg">
                {providers.map((p) => (
                  <button key={p.id} type="button" onClick={() => openCreate(p)}
                    className="block w-full px-3.5 py-2 text-start text-[13px] text-ink-secondary transition-colors hover:bg-canvas hover:text-ink">
                    {p.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="mt-5 overflow-hidden rounded-xl border border-border/70 bg-surface/40">
        <table className="w-full">
          <thead>
            <tr className="border-b border-border/60 text-[11px] uppercase tracking-wide text-ink-faint">
              <th className={`${cell} text-start font-medium`}>{t("channels.col.name")}</th>
              <th className={`${cell} text-start font-medium`}>{t("channels.col.provider")}</th>
              <th className={`${cell} text-start font-medium`}>{t("channels.col.kind")}</th>
              <th className={`${cell} text-start font-medium`}>{t("channels.col.model")}</th>
              <th className={`${cell} text-start font-medium`}>{t("channels.col.status")}</th>
              <th className={`${cell} w-10`} />
            </tr>
          </thead>
          <tbody className="divide-y divide-border/50">
            {rows.map((c) => (
              <tr key={c.id} className="transition-colors hover:bg-surface">
                <td className={cell}>
                  <span className="text-ink">{c.name}</span>
                  {!c.has_key && <span className="ms-1.5 rounded bg-canvas px-1 py-px text-[10px] text-ink-faint">{t("channels.noKey")}</span>}
                </td>
                <td className={`${cell} text-ink-secondary`}>{providerLabel(c.provider)}</td>
                <td className={`${cell} text-ink-secondary`}>{t(`channels.kind.${c.kind}`, { defaultValue: c.kind })}</td>
                <td className={`${cell} font-mono text-xs text-ink-secondary`}>{c.model ?? "—"}</td>
                <td className={cell}><StatusBadge status={c.enabled ? "active" : "suspended"} label={t(c.enabled ? "channels.on" : "channels.off")} /></td>
                <td className={cell}><RowMenu items={rowItems(c)} ariaLabel={t("common.actions")} /></td>
              </tr>
            ))}
            {!query.isLoading && rows.length === 0 && (
              <tr><td colSpan={6} className="px-3.5 py-12 text-center text-[13px] text-ink-faint">{t("channels.empty")}</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Create / edit modal (variant configuration) */}
      <Modal open={modalOpen} onClose={() => { setCreatePreset(null); setEditing(null); }}
        title={editing ? t("channels.editTitle") : t("channels.createTitle", { p: createPreset?.label ?? "" })}
        footer={<>
          <button type="button" onClick={() => { setCreatePreset(null); setEditing(null); }} className="rounded-(--radius-control) px-3.5 py-1.5 text-[13px] text-ink-secondary hover:bg-canvas">{t("common.cancel")}</button>
          <button type="button" onClick={onSave} disabled={busy || !name.trim()} className="rounded-(--radius-control) bg-accent px-3.5 py-1.5 text-[13px] font-medium text-white hover:bg-accent-hover disabled:opacity-50">{busy ? t("common.saving") : t("common.save")}</button>
        </>}>
        <div className="space-y-3.5">
          <div className="grid grid-cols-2 gap-3">
            <label className="block text-sm font-medium text-ink">{t("channels.fName")}
              <input value={name} onChange={(e) => setName(e.target.value)} autoFocus disabled={busy} className={`mt-1.5 ${FIELD}`} /></label>
            <label className="block text-sm font-medium text-ink">{t("channels.fKind")}
              <Select className="mt-1.5" value={kind} onChange={(v) => setKind(v as ChannelKind)} disabled={busy}
                options={KINDS.map((k) => ({ value: k, label: t(`channels.kind.${k}`) }))} /></label>
          </div>
          <label className="block text-sm font-medium text-ink">{t("channels.fBaseUrl")}
            <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://api.example.com/v1" disabled={busy} className={`mt-1.5 ${FIELD}`} /></label>
          {needsModel && (
            <label className="block text-sm font-medium text-ink">{t("channels.fModel")}
              <input value={model} onChange={(e) => setModel(e.target.value)} placeholder="e.g. deepseek-chat" disabled={busy} className={`mt-1.5 ${FIELD}`} /></label>
          )}
          <label className="block text-sm font-medium text-ink">{t("channels.fKey")}
            <input type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} autoComplete="new-password"
              placeholder={editing?.has_key ? t("channels.fKeyKept") : ""} disabled={busy} className={`mt-1.5 ${FIELD}`} /></label>
          {formProvider?.key_hint && (
            <p className="rounded-(--radius-control) bg-accent-soft px-3 py-2 text-xs text-accent">{formProvider.key_hint}</p>
          )}
          {err && <p className="text-[13px] text-danger">{err}</p>}
        </div>
      </Modal>

      <ConfirmDeleteModal open={!!delT} onClose={() => setDelT(null)} title={t("channels.deleteTitle")}
        target={delT?.name ?? ""} desc={t("channels.deleteDesc", { name: delT?.name ?? "" })}
        onConfirm={onDelete} busy={busy} error={err} />

      <Toast toast={toast} onDone={() => setToast(null)} />
    </div>
  );
}

type ChannelProviderLike = ChannelItem["provider"];
