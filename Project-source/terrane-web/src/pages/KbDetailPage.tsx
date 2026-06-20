/** 知识库详情 —— 左:源列表 + 添加文本;右:检索框 + 命中切片(知识复利第一段的可视化)。 */

import { ArrowLeft, FileText, MagnifyingGlass, Plus, PlugsConnected, Trash, UploadSimple, UserPlus, Users, X } from "@phosphor-icons/react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router";

import { KbChat } from "@/components/KbChat";
import { KbGraph } from "@/components/KbGraph";
import { KbMcpModal } from "@/components/KbMcpModal";
import { KbWiki } from "@/components/KbWiki";
import { StudioPanel } from "@/components/StudioPanel";
import { Select } from "@/components/ui/Select";
import { FALLBACK_LANG, isSupported } from "@/i18n/langs";
import { ApiError } from "@/lib/api";
import {
  addMember, addSource, deleteKb, deleteSource, getKb, listMembers, listSources, removeMember, searchKb, uploadSourceFile,
  type Kb, type KbMember, type KbSource, type SearchHit,
} from "@/lib/kb";

export function KbDetailPage() {
  const { t } = useTranslation();
  const { lang, kbId } = useParams();
  const navigate = useNavigate();
  const seg = lang && isSupported(lang) ? lang : FALLBACK_LANG;
  const id = kbId ?? "";

  const [kb, setKb] = useState<Kb | null>(null);
  const [sources, setSources] = useState<KbSource[]>([]);
  const [notFound, setNotFound] = useState(false);

  const [tab, setTab] = useState<"chat" | "search" | "studio" | "wiki" | "graph">("chat");
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const [searching, setSearching] = useState(false);

  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);

  const [mcpOpen, setMcpOpen] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);
  const [owner, setOwner] = useState<KbMember | null>(null);
  const [members, setMembers] = useState<KbMember[]>([]);
  const [shareEmail, setShareEmail] = useState("");
  const [shareRole, setShareRole] = useState<"viewer" | "editor">("viewer");
  const [shareErr, setShareErr] = useState("");
  const [shareBusy, setShareBusy] = useState(false);

  const loadMembers = useCallback(async () => {
    try { const r = await listMembers(id); setOwner(r.owner); setMembers(r.members); } catch { /* ignore */ }
  }, [id]);

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

  const reload = useCallback(async () => {
    try {
      const [k, s] = await Promise.all([getKb(id), listSources(id)]);
      setKb(k); setSources(s.items);
    } catch (e) {
      if (e instanceof ApiError && (e.status === 404 || e.status === 403)) setNotFound(true);
    }
  }, [id]);
  useEffect(() => { void reload(); }, [reload]);

  async function onSearch(e?: React.FormEvent) {
    e?.preventDefault();
    if (!q.trim()) { setHits(null); return; }
    setSearching(true);
    try { setHits((await searchKb(id, q.trim())).hits); } finally { setSearching(false); }
  }

  async function onAdd() {
    if (!title.trim() || !text.trim() || busy) return;
    setBusy(true); setErr("");
    try {
      await addSource(id, { title: title.trim(), text });
      setOpen(false); setTitle(""); setText("");
      await reload();
    } catch (e) {
      setErr(e instanceof ApiError ? t(`errors.${e.code}`, { defaultValue: e.message }) : t("errors.SYSTEM_HTTP_ERROR"));
    } finally { setBusy(false); }
  }

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";  // 允许重复选同一文件
    if (!file) return;
    if (file.size > 30_000_000) { setErr(t("kb.fileTooBig")); return; }
    setUploading(true); setErr("");
    try {
      const r = await uploadSourceFile(id, file);  // 后端 Terrane Parse 解析(PDF/Office)或文本直读
      if (r.ok === false) { setErr(t("kb.parseFailed")); return; }
      await reload();
    } catch {
      setErr(t("errors.SYSTEM_HTTP_ERROR"));
    } finally { setUploading(false); }
  }

  async function onDeleteSource(s: KbSource) {
    if (!window.confirm(t("kb.confirmDeleteSource", { name: s.title }))) return;
    try { await deleteSource(id, s.id); await reload(); } catch { /* ignore */ }
  }

  async function onDeleteKb() {
    if (!kb?.is_owner || !window.confirm(t("kb.confirmDelete", { name: kb.name }))) return;
    try { await deleteKb(id); navigate(`/${seg}/`); } catch { /* ignore */ }
  }

  const canEdit = kb?.my_role === "owner" || kb?.my_role === "editor";
  const field = "w-full rounded-(--radius-control) border border-border bg-canvas px-3 py-2 text-sm text-ink outline-none focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/30";

  if (notFound) {
    return (
      <main className="flex min-h-[70vh] items-center justify-center">
        <div className="text-center">
          <p className="text-sm text-ink-secondary">{t("kb.notFound")}</p>
          <button onClick={() => navigate(`/${seg}/`)} className="mt-3 text-sm text-accent hover:underline">{t("kb.back")}</button>
        </div>
      </main>
    );
  }

  return (
    <div className="px-8 py-8">
        <div className="mx-auto max-w-6xl">
          <button onClick={() => navigate(`/${seg}/`)} className="flex items-center gap-1 text-sm text-ink-secondary hover:text-ink">
            <ArrowLeft className="size-4" /> {t("kb.back")}
          </button>
          <div className="mt-3 flex items-start justify-between">
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-ink">{kb?.name ?? "…"}</h1>
              {kb?.description && <p className="mt-1 text-sm text-ink-secondary">{kb.description}</p>}
            </div>
            {kb?.is_owner && (
              <div className="flex items-center gap-2">
                <button onClick={() => setMcpOpen(true)}
                  className="flex items-center gap-1.5 rounded-(--radius-control) border border-border px-3 py-1.5 text-sm text-ink-secondary transition hover:bg-canvas hover:text-ink">
                  <PlugsConnected className="size-4" /> MCP
                </button>
                <button onClick={() => { setShareOpen(true); setShareErr(""); void loadMembers(); }}
                  className="flex items-center gap-1.5 rounded-(--radius-control) border border-border px-3 py-1.5 text-sm text-ink-secondary transition hover:bg-canvas hover:text-ink">
                  <Users className="size-4" /> {t("kb.share")}
                </button>
                <button onClick={onDeleteKb} className="flex items-center gap-1.5 rounded-(--radius-control) border border-border px-3 py-1.5 text-sm text-danger transition hover:bg-danger-soft">
                  <Trash className="size-4" /> {t("kb.deleteKb")}
                </button>
              </div>
            )}
          </div>

          <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-[20rem_1fr]">
            {/* 源面板 */}
            <section className="rounded-xl border border-border/70 bg-surface/40 p-4">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold text-ink">{t("kb.sources")} <span className="text-ink-faint">({sources.length})</span></h2>
                {canEdit && (
                  <div className="flex items-center gap-1.5">
                    <button onClick={() => fileRef.current?.click()} disabled={uploading} title={t("kb.uploadFile")}
                      className="flex items-center gap-1 rounded-full border border-border px-2.5 py-1 text-xs font-medium text-ink-secondary hover:bg-canvas disabled:opacity-50">
                      <UploadSimple className="size-3.5" /> {uploading ? t("kb.ingesting") : t("kb.upload")}
                    </button>
                    <button onClick={() => { setOpen(true); setErr(""); }} className="flex items-center gap-1 rounded-full bg-accent px-2.5 py-1 text-xs font-medium text-white hover:bg-accent-hover">
                      <Plus className="size-3.5" /> {t("kb.addText")}
                    </button>
                    <input ref={fileRef} type="file" hidden accept=".txt,.md,.markdown,.csv,.json,.log,.pdf,.docx,.xlsx,.pptx,.mp4,.mov,.avi,.webm,.mkv,text/*,video/*" onChange={onFile} />
                  </div>
                )}
              </div>
              <div className="mt-3 space-y-2">
                {sources.length === 0 ? (
                  <p className="py-6 text-center text-xs text-ink-faint">{t("kb.noSources")}</p>
                ) : sources.map((s) => (
                  <div key={s.id} className="group/src flex items-start gap-2 rounded-(--radius-control) border border-border/50 bg-surface px-3 py-2">
                    <FileText className="mt-0.5 size-4 shrink-0 text-ink-faint" />
                    <div className="min-w-0 flex-1">
                      <p className="line-clamp-1 text-[13px] text-ink">{s.title}</p>
                      <p className="text-[11px] text-ink-faint">{t("kb.chunks", { n: s.chunk_count })} · {t(`kb.status.${s.status}`, { defaultValue: s.status })}</p>
                    </div>
                    {canEdit && (
                      <button onClick={() => onDeleteSource(s)} title={t("kb.deleteSource")}
                        className="shrink-0 rounded p-1 text-ink-faint opacity-0 transition hover:bg-danger-soft hover:text-danger group-hover/src:opacity-100">
                        <Trash className="size-3.5" />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </section>

            {/* 问答 / 检索 区 */}
            <section>
              <div className="mb-4 inline-flex rounded-full border border-border bg-surface/40 p-0.5 text-[13px]">
                {(["chat", "search", "studio", "wiki", "graph"] as const).map((tk) => (
                  <button key={tk} onClick={() => setTab(tk)}
                    className={`rounded-full px-4 py-1.5 font-medium transition ${tab === tk ? "bg-accent text-white" : "text-ink-secondary hover:text-ink"}`}>
                    {t("kb.tab_" + tk)}
                  </button>
                ))}
              </div>

              {tab === "chat" ? <KbChat kbId={id} />
                : tab === "studio" ? <StudioPanel kbId={id} />
                : tab === "wiki" ? <KbWiki kbId={id} canEdit={canEdit} />
                : tab === "graph" ? <KbGraph kbId={id} canEdit={canEdit} />
                : (
              <>
              <form onSubmit={onSearch} className="flex items-center gap-2">
                <div className="relative flex-1">
                  <MagnifyingGlass className="absolute start-3 top-1/2 size-4 -translate-y-1/2 text-ink-faint" />
                  <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("kb.searchPlaceholder")}
                    className={`${field} ps-9`} />
                </div>
                <button type="submit" disabled={searching} className="rounded-(--radius-control) bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-50">
                  {searching ? t("kb.searching") : t("kb.search")}
                </button>
              </form>

              <div className="mt-4">
                {hits === null ? (
                  <p className="py-12 text-center text-sm text-ink-faint">{t("kb.searchHint")}</p>
                ) : hits.length === 0 ? (
                  <p className="py-12 text-center text-sm text-ink-faint">{t("kb.noHits")}</p>
                ) : (
                  <div className="space-y-3">
                    <p className="text-xs text-ink-faint">{t("kb.hitsCount", { n: hits.length })}</p>
                    {hits.map((h) => (
                      <div key={h.chunk_id} className="rounded-xl border border-border/70 bg-surface/40 p-4">
                        <div className="flex items-center justify-between text-xs text-ink-faint">
                          <span className="flex items-center gap-1"><FileText className="size-3.5" /> {h.source_title}</span>
                          <span className="rounded bg-accent-soft px-1.5 py-0.5 text-accent">{h.score}</span>
                        </div>
                        <p className="mt-2 whitespace-pre-wrap text-[13px] leading-relaxed text-ink-secondary">{h.content}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
              </>
              )}
            </section>
          </div>
        </div>

      <KbMcpModal kbId={id} open={mcpOpen} onClose={() => setMcpOpen(false)} />

      {shareOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => setShareOpen(false)}>
          <div className="w-full max-w-md rounded-xl border border-border bg-surface p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h2 className="text-lg font-semibold text-ink">{t("kb.shareTitle")}</h2>
            <p className="mt-1 text-[13px] text-ink-secondary">{t("kb.shareDesc")}</p>
            <div className="mt-4 flex items-end gap-2">
              <label className="flex-1 text-sm font-medium text-ink">{t("kb.memberEmail")}
                <input value={shareEmail} onChange={(e) => setShareEmail(e.target.value)} placeholder="user@example.com" disabled={shareBusy}
                  className={`mt-1.5 ${field}`} /></label>
              <Select className="w-28" value={shareRole} onChange={(v) => setShareRole(v as "viewer" | "editor")} disabled={shareBusy}
                options={[{ value: "viewer", label: t("kb.role.viewer") }, { value: "editor", label: t("kb.role.editor") }]} />
              <button onClick={onAddMember} disabled={shareBusy || !shareEmail.trim()}
                className="flex items-center gap-1 rounded-(--radius-control) bg-accent px-3 py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-50">
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
            <div className="mt-5 flex justify-end">
              <button onClick={() => setShareOpen(false)} className="rounded-(--radius-control) px-3.5 py-1.5 text-sm text-ink-secondary hover:bg-canvas">{t("common.close", { defaultValue: "关闭" })}</button>
            </div>
          </div>
        </div>
      )}

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => setOpen(false)}>
          <div className="w-full max-w-lg rounded-xl border border-border bg-surface p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h2 className="text-lg font-semibold text-ink">{t("kb.addTextTitle")}</h2>
            <div className="mt-4 space-y-3.5">
              <label className="block text-sm font-medium text-ink">{t("kb.fSourceTitle")}
                <input value={title} onChange={(e) => setTitle(e.target.value)} autoFocus disabled={busy} className={`mt-1.5 ${field}`} /></label>
              <label className="block text-sm font-medium text-ink">{t("kb.fText")}
                <textarea value={text} onChange={(e) => setText(e.target.value)} rows={8} disabled={busy} className={`mt-1.5 ${field}`} /></label>
              {err && <p className="text-[13px] text-danger">{err}</p>}
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button type="button" onClick={() => setOpen(false)} className="rounded-(--radius-control) px-3.5 py-1.5 text-sm text-ink-secondary hover:bg-canvas">{t("common.cancel")}</button>
              <button type="button" onClick={onAdd} disabled={busy || !title.trim() || !text.trim()} className="rounded-(--radius-control) bg-accent px-3.5 py-1.5 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-50">{busy ? t("kb.ingesting") : t("kb.addText")}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
