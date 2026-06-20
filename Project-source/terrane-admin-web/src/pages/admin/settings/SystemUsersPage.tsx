/** 设置 → 操作员（System Users）。后台账号管理:列出/新建/编辑(角色·状态)/重置密码/删除。
 *  权限 platform.user.*（super_admin 写、admin 只读）。护栏:不能对自己/最后一个超管 禁用·降级·删除。 */

import { Key, MagnifyingGlass, PencilSimple, Plus, Trash } from "@phosphor-icons/react";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { useAuth } from "@/auth/AuthContext";
import { ConfirmDeleteModal } from "@/components/ConfirmDeleteModal";
import { Modal } from "@/components/Modal";
import { Pagination } from "@/components/Pagination";
import { RowMenu, type RowMenuItem } from "@/components/RowMenu";
import { Select } from "@/components/Select";
import { ApiError } from "@/lib/api";
import {
  createOperator, deleteOperator, resetOperatorPassword, updateOperator,
  useOperators, OPERATOR_PAGE_SIZE, type OperatorItem, type OperatorRole,
} from "@/lib/operators";
import { StatusBadge } from "@/pages/admin/WorkspacesPage";

function fmtDateTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, { year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit" });
}

const FIELD = "w-full rounded-(--radius-control) border border-border bg-canvas px-3 py-2 text-sm text-ink outline-none focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/30";
const ROLES: OperatorRole[] = ["super_admin", "admin", "auditor"];

export function SystemUsersPage() {
  const { t } = useTranslation();
  const { has, user: me } = useAuth();
  const qc = useQueryClient();

  const [input, setInput] = useState("");
  const [status, setStatus] = useState("");
  const [filters, setFilters] = useState<{ q?: string; status?: string }>({});
  const [page, setPage] = useState(1);
  const query = useOperators(filters, page);
  const rows = query.data?.items ?? [];
  const total = query.data?.total ?? 0;

  const canWrite = has("platform.user.write");
  const canDelete = has("platform.user.delete");
  const showMenu = canWrite || canDelete;

  // 创建
  const [createOpen, setCreateOpen] = useState(false);
  const [cEmail, setCEmail] = useState("");
  const [cUser, setCUser] = useState("");
  const [cPass, setCPass] = useState("");
  const [cRole, setCRole] = useState<OperatorRole>("admin");
  const [created, setCreated] = useState<{ email: string; password: string | null } | null>(null);
  // 编辑
  const [editing, setEditing] = useState<OperatorItem | null>(null);
  const [eUser, setEUser] = useState("");
  const [eRole, setERole] = useState<OperatorRole>("admin");
  const [eStatus, setEStatus] = useState<"active" | "disabled">("active");
  // 重置密码
  const [resetT, setResetT] = useState<OperatorItem | null>(null);
  const [resetPw, setResetPw] = useState<string | null>(null);
  // 删除
  const [delT, setDelT] = useState<OperatorItem | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  function apply(nextStatus = status) {
    setPage(1);
    setFilters({ q: input.trim() || undefined, status: nextStatus || undefined });
  }
  const invalidate = () => qc.invalidateQueries({ queryKey: ["operators"] });
  function toErr(e: unknown) { setErr(e instanceof ApiError ? t(`errors.${e.code}`) : t("errors.SYSTEM_HTTP_ERROR")); }

  async function onCreate() {
    if (!cEmail.trim() || !cUser.trim() || busy) return;
    setBusy(true); setErr("");
    try {
      const r = await createOperator({ email: cEmail.trim(), username: cUser.trim(),
        password: cPass || undefined, role: cRole });
      invalidate();
      setCreated({ email: r.email, password: r.generated_password });
    } catch (e) { toErr(e); } finally { setBusy(false); }
  }
  async function onSaveEdit() {
    if (!editing || busy) return;
    setBusy(true); setErr("");
    try {
      await updateOperator(editing.id, { username: eUser.trim() || null, role: eRole, status: eStatus });
      invalidate(); setEditing(null);
    } catch (e) { toErr(e); } finally { setBusy(false); }
  }
  async function onReset() {
    if (!resetT || busy) return;
    setBusy(true); setErr("");
    try { const r = await resetOperatorPassword(resetT.id); setResetPw(r.generated_password); }
    catch (e) { toErr(e); } finally { setBusy(false); }
  }
  async function onDelete() {
    if (!delT || busy) return;
    setBusy(true); setErr("");
    try { await deleteOperator(delT.id); invalidate(); setDelT(null); }
    catch (e) { toErr(e); } finally { setBusy(false); }
  }

  function rowItems(o: OperatorItem): RowMenuItem[] {
    const items: RowMenuItem[] = [];
    if (canWrite) {
      items.push({ label: t("members.edit"), icon: PencilSimple,
        onClick: () => { setEditing(o); setEUser(o.username); setERole(o.role); setEStatus(o.status); setErr(""); } });
      items.push({ label: t("members.resetPw"), icon: Key,
        onClick: () => { setResetT(o); setResetPw(null); setErr(""); } });
    }
    if (canDelete) items.push({ label: t("members.delete"), icon: Trash, danger: true,
      onClick: () => { setDelT(o); setErr(""); } });
    return items;
  }

  const cell = "px-3.5 py-2 text-[13px]";
  const roleOptions = ROLES.map((r) => ({ value: r, label: t(`admin.roles.${r}`) }));
  const statusOptions = [
    { value: "", label: t("common.all") },
    { value: "active", label: t("members.status.active") },
    { value: "disabled", label: t("members.status.disabled") },
  ];

  return (
    <div className="mx-auto max-w-5xl">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-ink">{t("operators.title")}</h1>
          <p className="mt-1 text-[13px] text-ink-secondary">{t("operators.desc")}</p>
        </div>
        {canWrite && (
          <button type="button" onClick={() => { setCEmail(""); setCUser(""); setCPass(""); setCRole("admin"); setCreated(null); setErr(""); setCreateOpen(true); }}
            className="flex shrink-0 items-center gap-1.5 rounded-full bg-accent px-3.5 py-1.5 text-[13px] font-medium text-white transition hover:bg-accent-hover">
            <Plus className="size-4" /> {t("operators.create")}
          </button>
        )}
      </div>

      <form onSubmit={(e) => { e.preventDefault(); apply(); }} className="mt-5 flex items-center gap-2">
        <div className="relative w-full max-w-xs">
          <MagnifyingGlass className="absolute inset-y-0 start-3 my-auto size-4 text-ink-faint" />
          <input value={input} onChange={(e) => setInput(e.target.value)} placeholder={t("operators.searchPlaceholder")}
            className="w-full rounded-full border border-border bg-canvas py-1.5 ps-9 pe-3 text-[13px] text-ink outline-none transition focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/30" />
        </div>
        <div className="w-36">
          <Select value={status} options={statusOptions} onChange={(v) => { setStatus(v); apply(v); }} ariaLabel={t("operators.col.status")} />
        </div>
        <button type="submit" className="rounded-full bg-accent px-3.5 py-1.5 text-[13px] font-medium text-white transition hover:bg-accent-hover">{t("common.search")}</button>
      </form>

      <div className="mt-4 overflow-hidden rounded-xl border border-border/70 bg-surface/40">
        <table className="w-full">
          <thead>
            <tr className="border-b border-border/60 text-[11px] uppercase tracking-wide text-ink-faint">
              <th className={`${cell} text-start font-medium`}>{t("operators.col.user")}</th>
              <th className={`${cell} text-start font-medium`}>{t("operators.col.role")}</th>
              <th className={`${cell} text-start font-medium`}>{t("operators.col.status")}</th>
              <th className={`${cell} text-start font-medium`}>{t("operators.col.lastLogin")}</th>
              <th className={`${cell} text-start font-medium`}>{t("operators.col.created")}</th>
              <th className={`${cell} w-10`} />
            </tr>
          </thead>
          <tbody className="divide-y divide-border/50">
            {rows.map((o) => (
              <tr key={o.id} className="transition-colors hover:bg-surface">
                <td className={cell}>
                  <span className="block text-ink">{o.username}{o.id === me?.id && <span className="ms-1.5 text-[11px] text-ink-faint">{t("operators.you")}</span>}</span>
                  <span className="block text-[11px] text-ink-faint">{o.email}</span>
                </td>
                <td className={`${cell} text-ink-secondary`}>{t(`admin.roles.${o.role}`, { defaultValue: o.role })}</td>
                <td className={cell}><StatusBadge status={o.status} label={t(`members.status.${o.status}`, { defaultValue: o.status })} /></td>
                <td className={`${cell} whitespace-nowrap text-ink-secondary tabular-nums`}>{o.last_login_at ? fmtDateTime(o.last_login_at) : t("members.never")}</td>
                <td className={`${cell} whitespace-nowrap text-ink-secondary tabular-nums`}>{fmtDateTime(o.created_at)}</td>
                <td className={cell}>{showMenu && <RowMenu items={rowItems(o)} ariaLabel={t("common.actions")} />}</td>
              </tr>
            ))}
            {!query.isLoading && rows.length === 0 && (
              <tr><td colSpan={6} className="px-3.5 py-12 text-center text-[13px] text-ink-faint">{t("operators.empty")}</td></tr>
            )}
            {query.isLoading && rows.length === 0 && (
              <tr><td colSpan={6} className="px-3.5 py-12 text-center text-[13px] text-ink-faint">{t("common.loading")}</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <Pagination page={page} total={total} pageSize={OPERATOR_PAGE_SIZE} onPage={setPage} />

      {/* 创建 */}
      <Modal open={createOpen} onClose={() => setCreateOpen(false)} title={created ? t("operators.createdTitle") : t("operators.createTitle")}
        footer={created ? (
          <button type="button" onClick={() => setCreateOpen(false)} className="rounded-(--radius-control) bg-accent px-3.5 py-1.5 text-[13px] font-medium text-white hover:bg-accent-hover">{t("common.done")}</button>
        ) : (
          <>
            <button type="button" onClick={() => setCreateOpen(false)} className="rounded-(--radius-control) px-3.5 py-1.5 text-[13px] text-ink-secondary hover:bg-canvas">{t("common.cancel")}</button>
            <button type="button" onClick={onCreate} disabled={busy || !cEmail.trim() || !cUser.trim()} className="rounded-(--radius-control) bg-accent px-3.5 py-1.5 text-[13px] font-medium text-white hover:bg-accent-hover disabled:opacity-50">{busy ? t("common.creating") : t("common.create")}</button>
          </>
        )}>
        {created ? (
          <div className="space-y-3">
            <p className="text-sm text-ink">{t("operators.createdDesc", { email: created.email })}</p>
            {created.password && <PasswordReveal pw={created.password} label={t("operators.genPassword")} hint={t("operators.genPasswordHint")} />}
          </div>
        ) : (
          <div className="space-y-3.5">
            <label className="block text-sm font-medium text-ink">{t("operators.fEmail")}
              <input type="email" value={cEmail} onChange={(e) => setCEmail(e.target.value)} autoFocus placeholder="ops@example.com" disabled={busy} className={`mt-1.5 ${FIELD}`} /></label>
            <label className="block text-sm font-medium text-ink">{t("operators.fUsername")}
              <input value={cUser} onChange={(e) => setCUser(e.target.value)} disabled={busy} className={`mt-1.5 ${FIELD}`} /></label>
            <label className="block text-sm font-medium text-ink">{t("operators.fRole")}
              <Select className="mt-1.5" value={cRole} onChange={(v) => setCRole(v as OperatorRole)} disabled={busy} options={roleOptions} /></label>
            <label className="block text-sm font-medium text-ink">{t("operators.fPassword")}
              <input type="text" value={cPass} onChange={(e) => setCPass(e.target.value)} placeholder={t("operators.fPasswordPlaceholder")} disabled={busy} autoComplete="off" className={`mt-1.5 ${FIELD}`} /></label>
            {err && <p className="text-[13px] text-danger">{err}</p>}
          </div>
        )}
      </Modal>

      {/* 编辑 */}
      <Modal open={!!editing} onClose={() => setEditing(null)} title={t("operators.editTitle")}
        footer={<>
          <button type="button" onClick={() => setEditing(null)} className="rounded-(--radius-control) px-3.5 py-1.5 text-[13px] text-ink-secondary hover:bg-canvas">{t("common.cancel")}</button>
          <button type="button" onClick={onSaveEdit} disabled={busy} className="rounded-(--radius-control) bg-accent px-3.5 py-1.5 text-[13px] font-medium text-white hover:bg-accent-hover disabled:opacity-50">{busy ? t("common.saving") : t("common.save")}</button>
        </>}>
        <div className="space-y-3.5">
          <p className="text-[13px] text-ink-secondary">{editing?.email}</p>
          <label className="block text-sm font-medium text-ink">{t("operators.fUsername")}
            <input value={eUser} onChange={(e) => setEUser(e.target.value)} disabled={busy} className={`mt-1.5 ${FIELD}`} /></label>
          <div className="grid grid-cols-2 gap-3">
            <label className="block text-sm font-medium text-ink">{t("operators.fRole")}
              <Select className="mt-1.5" value={eRole} onChange={(v) => setERole(v as OperatorRole)} disabled={busy} options={roleOptions} /></label>
            <label className="block text-sm font-medium text-ink">{t("operators.col.status")}
              <Select className="mt-1.5" value={eStatus} onChange={(v) => setEStatus(v as "active" | "disabled")} disabled={busy}
                options={[{ value: "active", label: t("members.status.active") }, { value: "disabled", label: t("members.status.disabled") }]} /></label>
          </div>
          {err && <p className="text-[13px] text-danger">{err}</p>}
        </div>
      </Modal>

      {/* 重置密码 */}
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
          <PasswordReveal pw={resetPw} label={t("operators.genPassword")} hint={t("operators.resetHint")} />
        ) : (
          <p className="text-sm text-ink-secondary">{t("operators.resetDesc", { email: resetT?.email ?? "" })}</p>
        )}
        {err && <p className="mt-3 text-[13px] text-danger">{err}</p>}
      </Modal>

      {/* 删除（输入邮箱确认） */}
      <ConfirmDeleteModal open={!!delT} onClose={() => setDelT(null)} title={t("operators.deleteTitle")}
        target={delT?.email ?? ""} desc={t("operators.deleteDesc", { email: delT?.email ?? "" })}
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
