/** Workspace management -- list + create + row actions (view members / add member / edit / delete). Compact and polished. */

import { MagnifyingGlass, PencilSimple, Plus, Trash, UserPlus, UsersThree } from "@phosphor-icons/react";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router";

import { useAuth } from "@/auth/AuthContext";
import { ConfirmDeleteModal } from "@/components/ConfirmDeleteModal";
import { Modal } from "@/components/Modal";
import { Pagination } from "@/components/Pagination";
import { RowMenu, type RowMenuItem } from "@/components/RowMenu";
import { Select } from "@/components/Select";
import { FALLBACK_LANG, isSupported } from "@/i18n/langs";
import { ApiError } from "@/lib/api";
import {
  createWorkspace, deleteWorkspace, updateWorkspace,
  useWorkspaces, WS_PAGE_SIZE, type WorkspaceItem,
} from "@/lib/workspaces";

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "2-digit", day: "2-digit" });
}

const FIELD = "w-full rounded-(--radius-control) border border-border bg-canvas px-3 py-2 text-sm text-ink outline-none focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/30";

export function WorkspacesPage() {
  const { t } = useTranslation();
  const { has } = useAuth();
  const { lang } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const seg = lang && isSupported(lang) ? lang : FALLBACK_LANG;

  const [input, setInput] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const query = useWorkspaces(q, page);
  const rows: WorkspaceItem[] = query.data?.items ?? [];
  const total = query.data?.total ?? 0;

  const canWrite = has("platform.workspace.write");
  const canAddMember = has("platform.user.write");

  // Create
  const [createOpen, setCreateOpen] = useState(false);
  const [name, setName] = useState("");
  const [kind, setKind] = useState("team");
  // Edit
  const [editing, setEditing] = useState<WorkspaceItem | null>(null);
  const [eName, setEName] = useState("");
  const [eStatus, setEStatus] = useState("active");
  // Delete
  const [delT, setDelT] = useState<WorkspaceItem | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  function submit(e: React.FormEvent) { e.preventDefault(); setPage(1); setQ(input.trim()); }
  const invalidate = () => qc.invalidateQueries({ queryKey: ["workspaces"] });
  function toErr(e: unknown) { setErr(e instanceof ApiError ? t(`errors.${e.code}`) : t("errors.SYSTEM_HTTP_ERROR")); }

  async function onCreate() {
    if (!name.trim() || busy) return;
    setBusy(true); setErr("");
    try { await createWorkspace({ name: name.trim(), kind }); invalidate(); setCreateOpen(false); setName(""); setKind("team"); }
    catch (e) { toErr(e); } finally { setBusy(false); }
  }
  async function onSaveEdit() {
    if (!editing || busy) return;
    setBusy(true); setErr("");
    try { await updateWorkspace(editing.id, { name: eName.trim() || undefined, status: eStatus }); invalidate(); setEditing(null); }
    catch (e) { toErr(e); } finally { setBusy(false); }
  }
  async function onDelete() {
    if (!delT || busy) return;
    setBusy(true); setErr("");
    try { await deleteWorkspace(delT.id); invalidate(); qc.invalidateQueries({ queryKey: ["members"] }); setDelT(null); }
    catch (e) { toErr(e); } finally { setBusy(false); }
  }

  function rowItems(w: WorkspaceItem): RowMenuItem[] {
    const items: RowMenuItem[] = [
      { label: t("ws.showMembers"), icon: UsersThree, onClick: () => navigate(`/${seg}/admin/members?workspace=${w.id}`) },
    ];
    if (canAddMember) items.push({ label: t("ws.addMember"), icon: UserPlus,
      onClick: () => navigate(`/${seg}/admin/members?workspace=${w.id}&create=1`) });
    if (canWrite) {
      items.push({ label: t("ws.edit"), icon: PencilSimple,
        onClick: () => { setEditing(w); setEName(w.name); setEStatus(w.status); setErr(""); } });
      items.push({ label: t("ws.delete"), icon: Trash, danger: true,
        onClick: () => { setDelT(w); setErr(""); } });
    }
    return items;
  }

  const cell = "px-3.5 py-2 text-[13px]";

  return (
    <div className="mx-auto max-w-5xl">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-ink">{t("ws.title")}</h1>
          <p className="mt-1 text-[13px] text-ink-secondary">{t("ws.desc")}</p>
        </div>
        {canWrite && (
          <button type="button" onClick={() => { setName(""); setKind("team"); setErr(""); setCreateOpen(true); }}
            className="flex shrink-0 items-center gap-1.5 rounded-full bg-accent px-3.5 py-1.5 text-[13px] font-medium text-white transition hover:bg-accent-hover">
            <Plus className="size-4" /> {t("ws.create")}
          </button>
        )}
      </div>

      <form onSubmit={submit} className="mt-5 flex items-center gap-2">
        <div className="relative w-full max-w-xs">
          <MagnifyingGlass className="absolute inset-y-0 start-3 my-auto size-4 text-ink-faint" />
          <input value={input} onChange={(e) => setInput(e.target.value)} placeholder={t("ws.searchPlaceholder")}
            className="w-full rounded-full border border-border bg-canvas py-1.5 ps-9 pe-3 text-[13px] text-ink outline-none transition focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/30" />
        </div>
        <button type="submit" className="rounded-full bg-accent px-3.5 py-1.5 text-[13px] font-medium text-white transition hover:bg-accent-hover">{t("common.search")}</button>
      </form>

      <div className="mt-4 overflow-hidden rounded-xl border border-border/70 bg-surface/40">
        <table className="w-full">
          <thead>
            <tr className="border-b border-border/60 text-[11px] uppercase tracking-wide text-ink-faint">
              <th className={`${cell} text-start font-medium`}>{t("ws.col.name")}</th>
              <th className={`${cell} text-start font-medium`}>{t("ws.col.kind")}</th>
              <th className={`${cell} text-start font-medium`}>{t("ws.col.status")}</th>
              <th className={`${cell} text-end font-medium`}>{t("ws.col.members")}</th>
              <th className={`${cell} text-start font-medium`}>{t("ws.col.created")}</th>
              <th className={`${cell} w-10`} />
            </tr>
          </thead>
          <tbody className="divide-y divide-border/50">
            {rows.map((w) => (
              <tr key={w.id} className="transition-colors hover:bg-surface">
                <td className={cell}><span className="text-ink">{w.name}</span><span className="ms-1.5 font-mono text-[11px] text-ink-faint">{w.slug}</span></td>
                <td className={`${cell} text-ink-secondary`}>{t(`ws.kind.${w.kind}`, { defaultValue: w.kind })}</td>
                <td className={cell}><StatusBadge status={w.status} label={t(`ws.status.${w.status}`, { defaultValue: w.status })} /></td>
                <td className={`${cell} text-end tabular-nums text-ink`}>{w.member_count}</td>
                <td className={`${cell} whitespace-nowrap text-ink-secondary tabular-nums`}>{fmtDate(w.created_at)}</td>
                <td className={cell}><RowMenu items={rowItems(w)} ariaLabel={t("common.actions")} /></td>
              </tr>
            ))}
            {!query.isLoading && rows.length === 0 && (
              <tr><td colSpan={6} className="px-3.5 py-12 text-center text-[13px] text-ink-faint">{t("ws.empty")}</td></tr>
            )}
            {query.isLoading && rows.length === 0 && (
              <tr><td colSpan={6} className="px-3.5 py-12 text-center text-[13px] text-ink-faint">{t("common.loading")}</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <Pagination page={page} total={total} pageSize={WS_PAGE_SIZE} onPage={setPage} />

      {/* Create */}
      <Modal open={createOpen} onClose={() => setCreateOpen(false)} title={t("ws.createTitle")}
        footer={<>
          <button type="button" onClick={() => setCreateOpen(false)} className="rounded-(--radius-control) px-3.5 py-1.5 text-[13px] text-ink-secondary hover:bg-canvas">{t("common.cancel")}</button>
          <button type="button" onClick={onCreate} disabled={busy || !name.trim()} className="rounded-(--radius-control) bg-accent px-3.5 py-1.5 text-[13px] font-medium text-white hover:bg-accent-hover disabled:opacity-50">{busy ? t("common.creating") : t("common.create")}</button>
        </>}>
        <div className="space-y-3.5">
          <label className="block text-sm font-medium text-ink">{t("ws.fName")}
            <input value={name} onChange={(e) => setName(e.target.value)} autoFocus placeholder={t("ws.fNamePlaceholder")} disabled={busy} className={`mt-1.5 ${FIELD}`} /></label>
          <label className="block text-sm font-medium text-ink">{t("ws.fKind")}
            <Select className="mt-1.5" value={kind} onChange={setKind} disabled={busy}
              options={[{ value: "team", label: t("ws.kind.team") }, { value: "personal", label: t("ws.kind.personal") }]} /></label>
          {err && <p className="text-[13px] text-danger">{err}</p>}
        </div>
      </Modal>

      {/* Edit */}
      <Modal open={!!editing} onClose={() => setEditing(null)} title={t("ws.editTitle")}
        footer={<>
          <button type="button" onClick={() => setEditing(null)} className="rounded-(--radius-control) px-3.5 py-1.5 text-[13px] text-ink-secondary hover:bg-canvas">{t("common.cancel")}</button>
          <button type="button" onClick={onSaveEdit} disabled={busy} className="rounded-(--radius-control) bg-accent px-3.5 py-1.5 text-[13px] font-medium text-white hover:bg-accent-hover disabled:opacity-50">{busy ? t("common.saving") : t("common.save")}</button>
        </>}>
        <div className="space-y-3.5">
          <label className="block text-sm font-medium text-ink">{t("ws.fName")}
            <input value={eName} onChange={(e) => setEName(e.target.value)} disabled={busy} className={`mt-1.5 ${FIELD}`} /></label>
          <label className="block text-sm font-medium text-ink">{t("ws.col.status")}
            <Select className="mt-1.5" value={eStatus} onChange={setEStatus} disabled={busy}
              options={[{ value: "active", label: t("ws.status.active") }, { value: "suspended", label: t("ws.status.suspended") }]} /></label>
          {err && <p className="text-[13px] text-danger">{err}</p>}
        </div>
      </Modal>

      {/* Delete (type-to-confirm by name) */}
      <ConfirmDeleteModal open={!!delT} onClose={() => setDelT(null)} title={t("ws.deleteTitle")}
        target={delT?.name ?? ""} desc={t("ws.deleteDesc", { name: delT?.name ?? "" })}
        onConfirm={onDelete} busy={busy} error={err} />
    </div>
  );
}

const STATUS_STYLE: Record<string, string> = {
  active: "bg-accent-soft text-accent",
  suspended: "bg-canvas text-ink-faint",
  disabled: "bg-danger-soft text-danger",
  pending: "bg-canvas text-ink-secondary",
};

export function StatusBadge({ status, label }: { status: string; label: string }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ${STATUS_STYLE[status] ?? "bg-canvas text-ink-secondary"}`}>
      {label}
    </span>
  );
}
