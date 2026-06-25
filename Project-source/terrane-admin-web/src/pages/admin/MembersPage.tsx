/** Member management —— list + create + row actions (edit / reset password / delete). Compact and refined.
 *  Supports ?workspace=<id> to view only one workspace's members, and ?create=1 to auto-open the create dialog (with the workspace preselected). */

import { Key, MagnifyingGlass, PencilSimple, Plus, Trash } from "@phosphor-icons/react";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router";

import { useAuth } from "@/auth/AuthContext";
import { ConfirmDeleteModal } from "@/components/ConfirmDeleteModal";
import { Modal } from "@/components/Modal";
import { Pagination } from "@/components/Pagination";
import { RowMenu, type RowMenuItem } from "@/components/RowMenu";
import { Select } from "@/components/Select";
import { ApiError } from "@/lib/api";
import {
  createMember, deleteMember, resetMemberPassword, updateMember,
  useMembers, MEMBER_PAGE_SIZE, type MemberItem,
} from "@/lib/members";
import { useWorkspaces } from "@/lib/workspaces";
import { StatusBadge } from "@/pages/admin/WorkspacesPage";

function fmtDateTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, { year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit" });
}

const FIELD = "w-full rounded-(--radius-control) border border-border bg-canvas px-3 py-2 text-sm text-ink outline-none focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/30";

export function MembersPage() {
  const { t } = useTranslation();
  const { has } = useAuth();
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const wsFilter = params.get("workspace") ?? undefined;

  const [input, setInput] = useState("");
  const [status, setStatus] = useState("");
  const [filters, setFilters] = useState<{ q?: string; status?: string; workspace_id?: string }>({ workspace_id: wsFilter });
  const [page, setPage] = useState(1);

  const query = useMembers(filters, page);
  const rows: MemberItem[] = query.data?.items ?? [];
  const total = query.data?.total ?? 0;
  const wsList = useWorkspaces("", 1, 100);
  const wsOptions = (wsList.data?.items ?? []).map((w) => ({ value: w.id, label: w.name }));

  const canWrite = has("platform.user.write");
  const canDelete = has("platform.user.delete");

  // Create
  const [createOpen, setCreateOpen] = useState(false);
  const [cEmail, setCEmail] = useState("");
  const [cUser, setCUser] = useState("");
  const [cPass, setCPass] = useState("");
  const [cWs, setCWs] = useState("");
  const [cRole, setCRole] = useState("Owner");
  const [created, setCreated] = useState<{ email: string; password: string | null } | null>(null);
  // Edit
  const [editing, setEditing] = useState<MemberItem | null>(null);
  const [eUser, setEUser] = useState("");
  const [eStatus, setEStatus] = useState("active");
  // Reset password
  const [resetT, setResetT] = useState<MemberItem | null>(null);
  const [resetPw, setResetPw] = useState<string | null>(null);
  // Delete
  const [delT, setDelT] = useState<MemberItem | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  // ?create=1 -> open the create dialog (with the workspace preselected).
  useEffect(() => {
    if (params.get("create") === "1") {
      setCEmail(""); setCUser(""); setCPass(""); setCRole("Owner"); setCreated(null); setErr("");
      setCWs(wsFilter ?? "");
      setCreateOpen(true);
      params.delete("create");
      setParams(params, { replace: true });
    }
  }, [params, setParams, wsFilter]);

  function apply(nextStatus = status) {
    setPage(1);
    setFilters({ q: input.trim() || undefined, status: nextStatus || undefined, workspace_id: wsFilter });
  }
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["members"] });
    qc.invalidateQueries({ queryKey: ["workspaces"] });
  };
  function toErr(e: unknown) {
    setErr(e instanceof ApiError ? t(`errors.${e.code}`) : t("errors.SYSTEM_HTTP_ERROR"));
  }

  async function onCreate() {
    if (!cEmail.trim() || !cWs || busy) return;
    setBusy(true); setErr("");
    try {
      const r = await createMember({ email: cEmail.trim(), username: cUser.trim() || undefined,
        password: cPass || undefined, workspace_id: cWs, role: cRole });
      invalidate();
      setCreated({ email: r.email, password: r.generated_password });
    } catch (e) { toErr(e); } finally { setBusy(false); }
  }
  async function onSaveEdit() {
    if (!editing || busy) return;
    setBusy(true); setErr("");
    try {
      await updateMember(editing.id, { username: eUser.trim() || null, status: eStatus });
      invalidate(); setEditing(null);
    } catch (e) { toErr(e); } finally { setBusy(false); }
  }
  async function onReset() {
    if (!resetT || busy) return;
    setBusy(true); setErr("");
    try {
      const r = await resetMemberPassword(resetT.id);
      setResetPw(r.generated_password);
    } catch (e) { toErr(e); } finally { setBusy(false); }
  }
  async function onDelete() {
    if (!delT || busy) return;
    setBusy(true); setErr("");
    try { await deleteMember(delT.id); invalidate(); setDelT(null); }
    catch (e) { toErr(e); } finally { setBusy(false); }
  }

  function rowItems(m: MemberItem): RowMenuItem[] {
    const items: RowMenuItem[] = [];
    if (canWrite) {
      items.push({ label: t("members.edit"), icon: PencilSimple,
        onClick: () => { setEditing(m); setEUser(m.username ?? ""); setEStatus(m.status === "pending" ? "active" : m.status); setErr(""); } });
      items.push({ label: t("members.resetPw"), icon: Key,
        onClick: () => { setResetT(m); setResetPw(null); setErr(""); } });
    }
    if (canDelete) items.push({ label: t("members.delete"), icon: Trash, danger: true,
      onClick: () => { setDelT(m); setErr(""); } });
    return items;
  }

  const cell = "px-3.5 py-2 text-[13px]";
  const statusOptions = [
    { value: "", label: t("common.all") },
    { value: "active", label: t("members.status.active") },
    { value: "pending", label: t("members.status.pending") },
    { value: "disabled", label: t("members.status.disabled") },
  ];
  const roleOptions = (["Owner", "Admin", "Editor", "Member", "Reader"] as const).map((r) => ({ value: r, label: t(`members.role.${r}`) }));
  const showMenu = canWrite || canDelete;

  return (
    <div className="mx-auto max-w-5xl">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-ink">{t("members.title")}</h1>
          <p className="mt-1 text-[13px] text-ink-secondary">{t("members.desc")}</p>
        </div>
        {canWrite && (
          <button type="button" onClick={() => { setCEmail(""); setCUser(""); setCPass(""); setCWs(wsFilter ?? ""); setCRole("Owner"); setCreated(null); setErr(""); setCreateOpen(true); }}
            className="flex shrink-0 items-center gap-1.5 rounded-full bg-accent px-3.5 py-1.5 text-[13px] font-medium text-white transition hover:bg-accent-hover">
            <Plus className="size-4" /> {t("members.create")}
          </button>
        )}
      </div>

      {wsFilter && (
        <div className="mt-3 inline-flex items-center gap-2 rounded-full bg-accent-soft px-3 py-1 text-[13px] text-accent">
          {t("members.filteredByWs")}
          <button type="button" onClick={() => { params.delete("workspace"); setParams(params, { replace: true }); setFilters((f) => ({ ...f, workspace_id: undefined })); }}
            className="font-medium underline-offset-2 hover:underline">{t("members.clearWsFilter")}</button>
        </div>
      )}

      <form onSubmit={(e) => { e.preventDefault(); apply(); }} className="mt-5 flex items-center gap-2">
        <div className="relative w-full max-w-xs">
          <MagnifyingGlass className="absolute inset-y-0 start-3 my-auto size-4 text-ink-faint" />
          <input value={input} onChange={(e) => setInput(e.target.value)} placeholder={t("members.searchPlaceholder")}
            className="w-full rounded-full border border-border bg-canvas py-1.5 ps-9 pe-3 text-[13px] text-ink outline-none transition focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/30" />
        </div>
        <div className="w-36">
          <Select value={status} options={statusOptions} onChange={(v) => { setStatus(v); apply(v); }} ariaLabel={t("members.col.status")} />
        </div>
        <button type="submit" className="rounded-full bg-accent px-3.5 py-1.5 text-[13px] font-medium text-white transition hover:bg-accent-hover">
          {t("common.search")}
        </button>
      </form>

      <div className="mt-4 overflow-hidden rounded-xl border border-border/70 bg-surface/40">
        <table className="w-full">
          <thead>
            <tr className="border-b border-border/60 text-[11px] uppercase tracking-wide text-ink-faint">
              <th className={`${cell} text-start font-medium`}>{t("members.col.user")}</th>
              <th className={`${cell} text-start font-medium`}>{t("members.col.workspace")}</th>
              <th className={`${cell} text-start font-medium`}>{t("members.col.role")}</th>
              <th className={`${cell} text-start font-medium`}>{t("members.col.status")}</th>
              <th className={`${cell} text-start font-medium`}>{t("members.col.lastLogin")}</th>
              <th className={`${cell} text-start font-medium`}>{t("members.col.created")}</th>
              <th className={`${cell} w-10`} />
            </tr>
          </thead>
          <tbody className="divide-y divide-border/50">
            {rows.map((m) => (
              <tr key={m.id} className="transition-colors hover:bg-surface">
                <td className={cell}>
                  <span className="block text-ink">{m.username ?? m.email.split("@")[0]}</span>
                  <span className="block text-[11px] text-ink-faint">{m.email}</span>
                </td>
                <td className={`${cell} text-ink-secondary`}>{m.workspace_name}</td>
                <td className={`${cell} text-ink-secondary`}>{t(`members.role.${m.role}`, { defaultValue: m.role })}</td>
                <td className={cell}><StatusBadge status={m.status} label={t(`members.status.${m.status}`, { defaultValue: m.status })} /></td>
                <td className={`${cell} whitespace-nowrap text-ink-secondary tabular-nums`}>{m.last_login_at ? fmtDateTime(m.last_login_at) : t("members.never")}</td>
                <td className={`${cell} whitespace-nowrap text-ink-secondary tabular-nums`}>{fmtDateTime(m.created_at)}</td>
                <td className={cell}>{showMenu && <RowMenu items={rowItems(m)} ariaLabel={t("common.actions")} />}</td>
              </tr>
            ))}
            {!query.isLoading && rows.length === 0 && (
              <tr><td colSpan={7} className="px-3.5 py-12 text-center text-[13px] text-ink-faint">{t("members.empty")}</td></tr>
            )}
            {query.isLoading && rows.length === 0 && (
              <tr><td colSpan={7} className="px-3.5 py-12 text-center text-[13px] text-ink-faint">{t("common.loading")}</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <Pagination page={page} total={total} pageSize={MEMBER_PAGE_SIZE} onPage={setPage} />

      {/* Create */}
      <Modal open={createOpen} onClose={() => setCreateOpen(false)} title={created ? t("members.createdTitle") : t("members.createTitle")}
        footer={created ? (
          <button type="button" onClick={() => setCreateOpen(false)} className="rounded-(--radius-control) bg-accent px-3.5 py-1.5 text-[13px] font-medium text-white hover:bg-accent-hover">{t("common.done")}</button>
        ) : (
          <>
            <button type="button" onClick={() => setCreateOpen(false)} className="rounded-(--radius-control) px-3.5 py-1.5 text-[13px] text-ink-secondary hover:bg-canvas">{t("common.cancel")}</button>
            <button type="button" onClick={onCreate} disabled={busy || !cEmail.trim() || !cWs} className="rounded-(--radius-control) bg-accent px-3.5 py-1.5 text-[13px] font-medium text-white hover:bg-accent-hover disabled:opacity-50">{busy ? t("common.creating") : t("common.create")}</button>
          </>
        )}>
        {created ? (
          <div className="space-y-3">
            <p className="text-sm text-ink">{t("members.createdDesc", { email: created.email })}</p>
            {created.password && <PasswordReveal pw={created.password} label={t("members.genPassword")} hint={t("members.genPasswordHint")} />}
          </div>
        ) : (
          <div className="space-y-3.5">
            <label className="block text-sm font-medium text-ink">{t("members.fEmail")}
              <input type="email" value={cEmail} onChange={(e) => setCEmail(e.target.value)} autoFocus placeholder="user@example.com" disabled={busy} className={`mt-1.5 ${FIELD}`} /></label>
            <label className="block text-sm font-medium text-ink">{t("members.fUsername")}
              <input value={cUser} onChange={(e) => setCUser(e.target.value)} disabled={busy} className={`mt-1.5 ${FIELD}`} /></label>
            <div className="grid grid-cols-2 gap-3">
              <label className="block text-sm font-medium text-ink">{t("members.fWorkspace")}
                <Select className="mt-1.5" value={cWs} onChange={setCWs} disabled={busy} placeholder={t("members.fWorkspacePick")} options={wsOptions} /></label>
              <label className="block text-sm font-medium text-ink">{t("members.fRole")}
                <Select className="mt-1.5" value={cRole} onChange={setCRole} disabled={busy} options={roleOptions} /></label>
            </div>
            <label className="block text-sm font-medium text-ink">{t("members.fPassword")}
              <input type="text" value={cPass} onChange={(e) => setCPass(e.target.value)} placeholder={t("members.fPasswordPlaceholder")} disabled={busy} autoComplete="off" className={`mt-1.5 ${FIELD}`} /></label>
            {err && <p className="text-[13px] text-danger">{err}</p>}
          </div>
        )}
      </Modal>

      {/* Edit */}
      <Modal open={!!editing} onClose={() => setEditing(null)} title={t("members.editTitle")}
        footer={<>
          <button type="button" onClick={() => setEditing(null)} className="rounded-(--radius-control) px-3.5 py-1.5 text-[13px] text-ink-secondary hover:bg-canvas">{t("common.cancel")}</button>
          <button type="button" onClick={onSaveEdit} disabled={busy} className="rounded-(--radius-control) bg-accent px-3.5 py-1.5 text-[13px] font-medium text-white hover:bg-accent-hover disabled:opacity-50">{busy ? t("common.saving") : t("common.save")}</button>
        </>}>
        <div className="space-y-3.5">
          <p className="text-[13px] text-ink-secondary">{editing?.email}</p>
          <label className="block text-sm font-medium text-ink">{t("members.fUsername")}
            <input value={eUser} onChange={(e) => setEUser(e.target.value)} disabled={busy} className={`mt-1.5 ${FIELD}`} /></label>
          <label className="block text-sm font-medium text-ink">{t("members.col.status")}
            <Select className="mt-1.5" value={eStatus} onChange={setEStatus} disabled={busy}
              options={[{ value: "active", label: t("members.status.active") }, { value: "disabled", label: t("members.status.disabled") }]} /></label>
          {err && <p className="text-[13px] text-danger">{err}</p>}
        </div>
      </Modal>

      {/* Reset password */}
      <Modal open={!!resetT} onClose={() => setResetT(null)} title={t("members.resetTitle")}
        footer={resetPw ? (
          <button type="button" onClick={() => setResetT(null)} className="rounded-(--radius-control) bg-accent px-3.5 py-1.5 text-[13px] font-medium text-white hover:bg-accent-hover">{t("common.done")}</button>
        ) : (
          <>
            <button type="button" onClick={() => setResetT(null)} className="rounded-(--radius-control) px-3.5 py-1.5 text-[13px] text-ink-secondary hover:bg-canvas">{t("common.cancel")}</button>
            <button type="button" onClick={onReset} disabled={busy} className="rounded-(--radius-control) bg-accent px-3.5 py-1.5 text-[13px] font-medium text-white hover:bg-accent-hover disabled:opacity-50">{busy ? t("common.loading") : t("members.resetConfirm")}</button>
          </>
        )}>
        {resetPw ? (
          <PasswordReveal pw={resetPw} label={t("members.genPassword")} hint={t("members.genPasswordHint")} />
        ) : (
          <p className="text-sm text-ink-secondary">{t("members.resetDesc", { email: resetT?.email ?? "" })}</p>
        )}
        {err && <p className="mt-3 text-[13px] text-danger">{err}</p>}
      </Modal>

      {/* Delete (type-to-confirm email) */}
      <ConfirmDeleteModal open={!!delT} onClose={() => setDelT(null)} title={t("members.deleteTitle")}
        target={delT?.email ?? ""} desc={t("members.deleteDesc", { email: delT?.email ?? "" })}
        onConfirm={onDelete} busy={busy} error={err} />
    </div>
  );
}

function PasswordReveal({ pw, label, hint }: { pw: string; label: string; hint: string }) {
  return (
    <div className="rounded-(--radius-control) border border-border bg-canvas px-3 py-2.5">
      <p className="text-[11px] uppercase tracking-wide text-ink-faint">{label}</p>
      <p className="mt-1 select-all font-mono text-sm text-ink">{pw}</p>
      <p className="mt-1.5 text-[11px] text-ink-faint">{hint}</p>
    </div>
  );
}
