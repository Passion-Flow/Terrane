/** 知识库详情 —— 左:源列表(状态/重解析/上传分档);右:概览/问答/检索/Studio/Wiki/图谱。 */

import {
  ArrowLeft, ArrowsClockwise, ChartBar, ChatCircleText, CircleNotch, Eye, FileText, FunnelSimple,
  Graph as GraphIcon, MagnifyingGlass, Plus, PlugsConnected, Sparkle, TextT, Trash, UploadSimple,
  UserPlus, Users, WarningCircle, X, type Icon,
} from "@phosphor-icons/react";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router";

import { KbChat } from "@/components/KbChat";
import { KbGraph } from "@/components/KbGraph";
import { KbMcpModal } from "@/components/KbMcpModal";
import { KbWiki } from "@/components/KbWiki";
import { StudioPanel } from "@/components/StudioPanel";
import { Modal } from "@/components/ui/Modal";
import { Select } from "@/components/ui/Select";
import { FALLBACK_LANG, isSupported } from "@/i18n/langs";
import { ApiError } from "@/lib/api";
import {
  addMember, addSource, deleteKb, deleteSource, getKb, lintKb, listMembers, listSources, removeMember,
  reparseSource, searchKb, uploadSourceFile,
  type KbLint, type Kb, type KbMember, type KbSource, type ParseTier, type SearchHit,
} from "@/lib/kb";

type Tab = "overview" | "chat" | "search" | "studio" | "wiki" | "graph";
const TABS: { k: Tab; icon: Icon }[] = [
  { k: "overview", icon: ChartBar },
  { k: "chat", icon: ChatCircleText },
  { k: "search", icon: MagnifyingGlass },
  { k: "studio", icon: Sparkle },
  { k: "wiki", icon: FileText },
  { k: "graph", icon: GraphIcon },
];
const TIERS: ParseTier[] = ["fast", "standard", "high"];
const POLL_MS = 2500;
const PARSING = new Set(["pending", "parsing"]);

export function KbDetailPage() {
  const { t } = useTranslation();
  const { lang, kbId } = useParams();
  const navigate = useNavigate();
  const seg = lang && isSupported(lang) ? lang : FALLBACK_LANG;
  const id = kbId ?? "";

  const [kb, setKb] = useState<Kb | null>(null);
  const [sources, setSources] = useState<KbSource[]>([]);
  const [notFound, setNotFound] = useState(false);

  const [tab, setTab] = useState<Tab>("overview");
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const [searching, setSearching] = useState(false);

  // overview stats
  const [lint, setLint] = useState<KbLint | null>(null);

  // source filtering
  const [filter, setFilter] = useState("");
  const [sort, setSort] = useState<"newest" | "oldest">("newest");

  // add text modal
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  // upload modal (tier select)
  const [uploadOpen, setUploadOpen] = useState(false);
  const [tier, setTier] = useState<ParseTier>("standard");
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  // reparse modal
  const [reparseFor, setReparseFor] = useState<KbSource | null>(null);
  const [reparseTier, setReparseTier] = useState<ParseTier>("high");
  const [reparsing, setReparsing] = useState(false);

  // delete source (type-to-confirm)
  const [delFor, setDelFor] = useState<KbSource | null>(null);
  const [delInput, setDelInput] = useState("");
  // delete kb (type-to-confirm)
  const [delKbOpen, setDelKbOpen] = useState(false);
  const [delKbInput, setDelKbInput] = useState("");

  // mobile source drawer
  const [drawer, setDrawer] = useState(false);

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

  const loadSources = useCallback(async () => {
    try { setSources((await listSources(id)).items); } catch { /* ignore */ }
  }, [id]);

  const loadStats = useCallback(async () => {
    try { setLint(await lintKb(id)); } catch { /* ignore */ }
  }, [id]);

  const reload = useCallback(async () => {
    try {
      const [k, s] = await Promise.all([getKb(id), listSources(id)]);
      setKb(k); setSources(s.items);
    } catch (e) {
      if (e instanceof ApiError && (e.status === 404 || e.status === 403)) setNotFound(true);
    }
  }, [id]);
  useEffect(() => { void reload(); }, [reload]);
  useEffect(() => { if (tab === "overview") void loadStats(); }, [tab, loadStats, sources.length]);

  // 轮询:有 pending/parsing 的源时每 ~2.5s 刷新源列表,直到全部 parsed/failed
  const hasParsing = useMemo(() => sources.some((s) => PARSING.has(s.status)), [sources]);
  useEffect(() => {
    if (!hasParsing) return;
    const h = window.setInterval(() => { void loadSources(); }, POLL_MS);
    return () => clearInterval(h);
  }, [hasParsing, loadSources]);

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
      await loadSources();
    } catch (e) {
      setErr(e instanceof ApiError ? t(`errors.${e.code}`, { defaultValue: e.message }) : t("errors.SYSTEM_HTTP_ERROR"));
    } finally { setBusy(false); }
  }

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (file.size > 300_000_000) { setErr(t("kb.fileTooBig")); return; }
    setUploading(true); setErr("");
    try {
      const r = await uploadSourceFile(id, file, tier);
      if (r.ok === false) { setErr(t("kb.parseFailed")); return; }
      setUploadOpen(false);
      await loadSources();  // 立即出现(parsing 态),轮询接管
    } catch {
      setErr(t("errors.SYSTEM_HTTP_ERROR"));
    } finally { setUploading(false); }
  }

  async function onReparse() {
    if (!reparseFor || reparsing) return;
    setReparsing(true);
    try {
      await reparseSource(id, reparseFor.id, reparseTier);
      setReparseFor(null);
      await loadSources();
    } catch { /* ignore */ }
    finally { setReparsing(false); }
  }

  async function onDeleteSource() {
    if (!delFor) return;
    try { await deleteSource(id, delFor.id); setDelFor(null); setDelInput(""); await loadSources(); } catch { /* ignore */ }
  }
  function onPreview(s: KbSource) {
    navigate(`/${seg}/kb/${id}/source/${s.id}`);
  }

  async function onDeleteKb() {
    if (!kb?.is_owner) return;
    try { await deleteKb(id); navigate(`/${seg}/`); } catch { /* ignore */ }
  }

  const canEdit = kb?.my_role === "owner" || kb?.my_role === "editor";
  const field = "w-full rounded-(--radius-control) border border-border bg-canvas px-3 py-2 text-sm text-ink outline-none focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/30";

  const tierOptions = TIERS.map((tk) => ({ value: tk, label: t(`kb.tier.${tk}`), hint: undefined }));

  const visibleSources = useMemo(() => {
    let arr = sources;
    const f = filter.trim().toLowerCase();
    if (f) arr = arr.filter((s) => s.title.toLowerCase().includes(f));
    arr = [...arr].sort((a, b) => {
      const ta = a.created_at ? Date.parse(a.created_at) : 0;
      const tb = b.created_at ? Date.parse(b.created_at) : 0;
      return sort === "newest" ? tb - ta : ta - tb;
    });
    return arr;
  }, [sources, filter, sort]);

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

  const sourcesPanel = (
    <section className="flex h-full flex-col rounded-xl border border-border/70 bg-surface/40 p-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-ink">{t("kb.sources")} <span className="text-ink-faint">({sources.length})</span></h2>
        {canEdit && (
          <div className="flex shrink-0 items-center gap-1.5">
            <button onClick={() => { setUploadOpen(true); setErr(""); setTier("standard"); }} title={t("kb.uploadFile")}
              className="flex items-center gap-1 rounded-full border border-border px-2.5 py-1 text-xs font-medium text-ink-secondary transition hover:bg-canvas hover:text-ink">
              <UploadSimple className="size-3.5" /> {t("kb.upload")}
            </button>
            <button onClick={() => { setOpen(true); setErr(""); }} title={t("kb.addText")}
              className="flex items-center gap-1 rounded-full bg-accent px-2.5 py-1 text-xs font-medium text-white transition hover:bg-accent-hover">
              <Plus className="size-3.5" />
            </button>
          </div>
        )}
      </div>

      {sources.length > 4 && (
        <div className="mt-3 flex items-center gap-1.5">
          <div className="relative flex-1">
            <MagnifyingGlass className="absolute start-2.5 top-1/2 size-3.5 -translate-y-1/2 text-ink-faint" />
            <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder={t("kb.sourceSearchPlaceholder")}
              className="w-full rounded-(--radius-control) border border-border bg-canvas py-1.5 ps-8 pe-2 text-xs text-ink outline-none focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/30" />
          </div>
          <button onClick={() => setSort((s) => (s === "newest" ? "oldest" : "newest"))}
            title={t(sort === "newest" ? "common.sortNewest" : "common.sortOldest")}
            className="flex shrink-0 items-center gap-1 rounded-(--radius-control) border border-border px-2 py-1.5 text-xs text-ink-secondary transition hover:bg-canvas hover:text-ink">
            <FunnelSimple className="size-3.5" />
          </button>
        </div>
      )}

      <div className="mt-3 flex-1 space-y-2 overflow-y-auto">
        {sources.length === 0 ? (
          <p className="py-6 text-center text-xs text-ink-faint">{t("kb.noSources")}</p>
        ) : visibleSources.length === 0 ? (
          <p className="py-6 text-center text-xs text-ink-faint">{t("kb.noMatch")}</p>
        ) : visibleSources.map((s) => {
          const parsing = PARSING.has(s.status);
          const failed = s.status === "failed";
          return (
            <div key={s.id} className="group/src rounded-(--radius-control) border border-border/50 bg-surface px-3 py-2 transition hover:border-border">
              <div className="flex items-start gap-2">
                {parsing
                  ? <CircleNotch className="mt-0.5 size-4 shrink-0 animate-spin text-accent" />
                  : failed
                    ? <WarningCircle className="mt-0.5 size-4 shrink-0 text-danger" weight="fill" />
                    : <FileText className="mt-0.5 size-4 shrink-0 text-ink-faint" />}
                <button onClick={() => onPreview(s)} title={t("kb.previewSource")} className="min-w-0 flex-1 text-start">
                  <p className="line-clamp-1 text-[13px] text-ink transition group-hover/src:text-accent">{s.title}</p>
                  <p className="mt-0.5 flex items-center gap-1 text-[11px]">
                    {parsing ? <span className="text-accent">{t("kb.statusParsing")}…</span>
                      : failed ? <span className="text-danger">{t("kb.statusFailed")}</span>
                        : <span className="text-ink-faint">{t("kb.chunks", { n: s.chunk_count })}</span>}
                  </p>
                </button>
                <div className="flex shrink-0 items-center gap-0.5">
                  <button onClick={() => onPreview(s)} title={t("kb.previewSource")}
                    className="rounded p-1 text-ink-faint opacity-0 transition hover:bg-accent-soft hover:text-accent group-hover/src:opacity-100">
                    <Eye className="size-3.5" />
                  </button>
                  {canEdit && (
                    <button onClick={() => { setDelFor(s); setDelInput(""); }} title={t("kb.deleteSource")}
                      className="rounded p-1 text-ink-faint opacity-0 transition hover:bg-danger-soft hover:text-danger group-hover/src:opacity-100">
                      <Trash className="size-3.5" />
                    </button>
                  )}
                </div>
              </div>
              {failed && canEdit && (
                <button onClick={() => { setReparseFor(s); setReparseTier("high"); }}
                  className="mt-1.5 flex w-full items-center justify-center gap-1 rounded-(--radius-control) border border-danger/30 bg-danger-soft py-1 text-[11px] font-medium text-danger transition hover:bg-danger-soft/70">
                  <ArrowsClockwise className="size-3" /> {t("kb.reparse")}
                </button>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );

  return (
    <div className="px-6 py-8 sm:px-8">
      <div className="mx-auto max-w-6xl">
        <button onClick={() => navigate(`/${seg}/`)} className="flex items-center gap-1 text-sm text-ink-secondary transition hover:text-ink">
          <ArrowLeft className="size-4" /> {t("kb.back")}
        </button>
        <div className="mt-3 flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h1 className="truncate text-2xl font-bold tracking-tight text-ink">{kb?.name ?? "…"}</h1>
            {kb?.description && <p className="mt-1 text-sm text-ink-secondary">{kb.description}</p>}
          </div>
          {kb?.is_owner && (
            <div className="flex flex-wrap items-center gap-2">
              <button onClick={() => setMcpOpen(true)}
                className="flex items-center gap-1.5 rounded-(--radius-control) border border-border px-3 py-1.5 text-sm text-ink-secondary transition hover:bg-canvas hover:text-ink">
                <PlugsConnected className="size-4" /> MCP
              </button>
              <button onClick={() => { setShareOpen(true); setShareErr(""); void loadMembers(); }}
                className="flex items-center gap-1.5 rounded-(--radius-control) border border-border px-3 py-1.5 text-sm text-ink-secondary transition hover:bg-canvas hover:text-ink">
                <Users className="size-4" /> {t("kb.share")}
              </button>
              <button onClick={() => { setDelKbOpen(true); setDelKbInput(""); }} className="flex items-center gap-1.5 rounded-(--radius-control) border border-border px-3 py-1.5 text-sm text-danger transition hover:bg-danger-soft">
                <Trash className="size-4" /> {t("kb.deleteKb")}
              </button>
            </div>
          )}
        </div>

        {/* 移动端:展开源抽屉触发 */}
        <button onClick={() => setDrawer(true)}
          className="mt-4 flex w-full items-center justify-center gap-1.5 rounded-(--radius-control) border border-border bg-surface/40 py-2 text-sm font-medium text-ink-secondary transition hover:text-ink lg:hidden">
          <FileText className="size-4" /> {t("kb.showSources")} ({sources.length})
        </button>

        <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-[20rem_1fr]">
          {/* 源面板:桌面常驻 */}
          <div className="hidden lg:block">{sourcesPanel}</div>

          {/* 主区 */}
          <section className="min-w-0">
            <div className="mb-4 inline-flex max-w-full flex-wrap gap-0.5 rounded-full border border-border bg-surface/40 p-0.5 text-[13px]">
              {TABS.map(({ k, icon: Ic }) => (
                <button key={k} onClick={() => setTab(k)}
                  className={`flex items-center gap-1.5 rounded-full px-3.5 py-1.5 font-medium transition ${tab === k ? "bg-accent text-white shadow-sm" : "text-ink-secondary hover:text-ink"}`}>
                  <Ic className="size-4" weight={tab === k ? "fill" : "regular"} /> {t("kb.tab_" + k)}
                </button>
              ))}
            </div>

            {tab === "overview" ? <Overview lint={lint} onRetry={loadStats} />
              : tab === "chat" ? <KbChat kbId={id} />
                : tab === "studio" ? <StudioPanel kbId={id} />
                  : tab === "wiki" ? <KbWiki kbId={id} canEdit={canEdit} />
                    : tab === "graph" ? <KbGraph kbId={id} canEdit={canEdit} />
                      : (
                        <>
                          <form onSubmit={onSearch} className="flex items-center gap-2">
                            <div className="relative flex-1">
                              <MagnifyingGlass className="absolute start-3 top-1/2 size-4 -translate-y-1/2 text-ink-faint" />
                              <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("kb.searchPlaceholder")} className={`${field} ps-9`} />
                            </div>
                            <button type="submit" disabled={searching} className="rounded-(--radius-control) bg-accent px-4 py-2 text-sm font-medium text-white transition hover:bg-accent-hover disabled:opacity-50">
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
                                {hits.map((h) => {
                                  const pct = Math.max(4, Math.min(100, Math.round(h.score * 100)));
                                  return (
                                    <button key={h.chunk_id} onClick={() => navigate(`/${seg}/kb/${id}/source/${h.source_id}`)}
                                      className="block w-full rounded-xl border border-border/70 bg-surface/40 p-4 text-start transition hover:-translate-y-0.5 hover:border-accent/50 hover:bg-surface hover:shadow-sm">
                                      <div className="flex items-center justify-between gap-2 text-xs text-ink-faint">
                                        <span className="flex min-w-0 items-center gap-1"><FileText className="size-3.5 shrink-0" /> <span className="truncate">{h.source_title}</span></span>
                                        <span className="flex shrink-0 items-center gap-1.5">
                                          <span className="h-1.5 w-16 overflow-hidden rounded-full bg-canvas">
                                            <span className="block h-full rounded-full bg-accent" style={{ width: `${pct}%` }} />
                                          </span>
                                          <span className="text-accent">{pct}%</span>
                                        </span>
                                      </div>
                                      <p className="mt-2 line-clamp-4 whitespace-pre-wrap text-[13px] leading-relaxed text-ink-secondary">{h.content}</p>
                                    </button>
                                  );
                                })}
                              </div>
                            )}
                          </div>
                        </>
                      )}
          </section>
        </div>
      </div>

      {/* 移动端源抽屉 */}
      {drawer && (
        <div className="fixed inset-0 z-50 flex lg:hidden" onClick={() => setDrawer(false)}>
          <div className="absolute inset-0 bg-black/45 backdrop-blur-[2px]" />
          <div className="relative ms-auto flex h-full w-80 max-w-[85vw] flex-col bg-canvas p-4 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <button onClick={() => setDrawer(false)} className="mb-2 self-end rounded-lg p-1.5 text-ink-faint transition hover:bg-surface hover:text-ink"><X className="size-4.5" /></button>
            <div className="min-h-0 flex-1">{sourcesPanel}</div>
          </div>
        </div>
      )}

      <input ref={fileRef} type="file" hidden accept=".txt,.md,.markdown,.csv,.json,.log,.pdf,.docx,.xlsx,.pptx,.mp4,.mov,.avi,.webm,.mkv,text/*,video/*" onChange={onFile} />

      <KbMcpModal kbId={id} open={mcpOpen} onClose={() => setMcpOpen(false)} />

      {/* 上传 — 选解析档位 */}
      <Modal open={uploadOpen} onClose={() => !uploading && setUploadOpen(false)} title={t("kb.uploadTitle")} desc={t("kb.uploadAccept")}>
        <div className="space-y-3">
          <p className="text-sm font-medium text-ink">{t("kb.uploadTierLabel")}</p>
          <div className="grid grid-cols-3 gap-2">
            {TIERS.map((tk) => (
              <button key={tk} type="button" onClick={() => setTier(tk)} disabled={uploading}
                className={`rounded-xl border px-2 py-2.5 text-center text-[13px] font-medium transition active:translate-y-px ${tier === tk ? "border-accent bg-accent-soft text-accent" : "border-border/70 text-ink-secondary hover:border-accent/40"}`}>
                {t(`kb.tier.${tk}`)}
              </button>
            ))}
          </div>
          <p className="rounded-(--radius-control) bg-canvas px-3 py-2 text-[12px] leading-relaxed text-ink-secondary">{t(`kb.tierHint.${tier}`)}</p>
          {err && <p className="text-[13px] text-danger">{err}</p>}
          <button type="button" onClick={() => fileRef.current?.click()} disabled={uploading}
            className="flex w-full items-center justify-center gap-1.5 rounded-(--radius-control) bg-accent px-3.5 py-2 text-sm font-medium text-white transition hover:bg-accent-hover disabled:opacity-60">
            {uploading ? <><CircleNotch className="size-4 animate-spin" /> {t("kb.ingesting")}</> : <><UploadSimple className="size-4" /> {t("kb.uploadChoose")}</>}
          </button>
        </div>
      </Modal>

      {/* 重新解析 */}
      <Modal open={!!reparseFor} onClose={() => !reparsing && setReparseFor(null)}
        title={reparseFor ? t("kb.reparseTitle", { name: reparseFor.title }) : ""} desc={t("kb.reparseDesc")}
        footer={
          <>
            <button onClick={() => setReparseFor(null)} disabled={reparsing} className="rounded-(--radius-control) px-3.5 py-1.5 text-sm text-ink-secondary transition hover:bg-canvas">{t("common.cancel")}</button>
            <button onClick={onReparse} disabled={reparsing} className="flex items-center gap-1.5 rounded-(--radius-control) bg-accent px-3.5 py-1.5 text-sm font-medium text-white transition hover:bg-accent-hover disabled:opacity-60">
              {reparsing ? <><CircleNotch className="size-4 animate-spin" /> {t("kb.reparsing")}</> : <><ArrowsClockwise className="size-4" /> {t("kb.reparse")}</>}
            </button>
          </>
        }>
        <div className="space-y-3">
          <p className="text-sm font-medium text-ink">{t("kb.uploadTierLabel")}</p>
          <Select value={reparseTier} onChange={(v) => setReparseTier(v as ParseTier)} options={tierOptions} disabled={reparsing} />
          <p className="rounded-(--radius-control) bg-canvas px-3 py-2 text-[12px] leading-relaxed text-ink-secondary">{t(`kb.tierHint.${reparseTier}`)}</p>
        </div>
      </Modal>

      {/* 删除源 — type-to-confirm */}
      <Modal open={!!delFor} onClose={() => { setDelFor(null); setDelInput(""); }} title={t("kb.deleteSource")}
        desc={delFor ? t("kb.confirmDeleteSource", { name: delFor.title }) : ""}
        footer={
          <>
            <button onClick={() => { setDelFor(null); setDelInput(""); }} className="rounded-(--radius-control) px-3.5 py-1.5 text-sm text-ink-secondary transition hover:bg-canvas">{t("common.cancel")}</button>
            <button onClick={onDeleteSource} disabled={delInput !== delFor?.title}
              className="rounded-(--radius-control) bg-danger px-3.5 py-1.5 text-sm font-medium text-white transition hover:opacity-90 disabled:opacity-40">{t("common.delete")}</button>
          </>
        }>
        <label className="block text-[13px] text-ink-secondary">{delFor && t("kb.typeToConfirm", { name: delFor.title })}
          <input value={delInput} onChange={(e) => setDelInput(e.target.value)} autoFocus className={`mt-1.5 ${field}`} /></label>
      </Modal>

      {/* 删除库 — type-to-confirm */}
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

      {/* 共享 */}
      <Modal open={shareOpen} onClose={() => setShareOpen(false)} title={t("kb.shareTitle")} desc={t("kb.shareDesc")}
        footer={<button onClick={() => setShareOpen(false)} className="rounded-(--radius-control) px-3.5 py-1.5 text-sm text-ink-secondary transition hover:bg-canvas">{t("common.close")}</button>}>
        <div className="flex items-end gap-2">
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
      </Modal>

      {/* 添加文本 */}
      <Modal open={open} onClose={() => setOpen(false)} title={t("kb.addTextTitle")} size="lg"
        footer={
          <>
            <button type="button" onClick={() => setOpen(false)} className="rounded-(--radius-control) px-3.5 py-1.5 text-sm text-ink-secondary transition hover:bg-canvas">{t("common.cancel")}</button>
            <button type="button" onClick={onAdd} disabled={busy || !title.trim() || !text.trim()} className="rounded-(--radius-control) bg-accent px-3.5 py-1.5 text-sm font-medium text-white transition hover:bg-accent-hover disabled:opacity-50">{busy ? t("kb.ingesting") : t("kb.addText")}</button>
          </>
        }>
        <div className="space-y-3.5">
          <label className="block text-sm font-medium text-ink">{t("kb.fSourceTitle")}
            <input value={title} onChange={(e) => setTitle(e.target.value)} autoFocus disabled={busy} className={`mt-1.5 ${field}`} /></label>
          <label className="block text-sm font-medium text-ink">{t("kb.fText")}
            <textarea value={text} onChange={(e) => setText(e.target.value)} rows={8} disabled={busy} className={`mt-1.5 ${field}`} /></label>
          {err && <p className="text-[13px] text-danger">{err}</p>}
        </div>
      </Modal>
    </div>
  );
}

/** 概览 tab —— 库统计九宫格 + 健康度 + 待办建议(复用 /lint)。 */
function Overview({ lint, onRetry }: { lint: KbLint | null; onRetry: () => void }) {
  const { t } = useTranslation();
  if (!lint) {
    return (
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {[...Array(5)].map((_, i) => <div key={i} className="h-24 animate-pulse rounded-xl border border-border/60 bg-surface/40" />)}
      </div>
    );
  }
  const s = lint.stats;
  const cards: { label: string; value: number | string; icon: Icon }[] = [
    { label: t("kb.ovSources"), value: s.sources, icon: FileText },
    { label: t("kb.ovChunks"), value: s.chunks, icon: TextT },
    { label: t("kb.ovEmbeds"), value: s.embedded_chunks, icon: Sparkle },
    { label: t("kb.ovGraphNodes"), value: s.graph_nodes, icon: GraphIcon },
    { label: t("kb.ovHealth"), value: `${lint.score}`, icon: ChartBar },
  ];
  const scoreColor = lint.score >= 80 ? "text-accent" : lint.score >= 50 ? "text-ink" : "text-danger";
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {cards.map((c) => {
          const Ic = c.icon;
          const isScore = c.label === t("kb.ovHealth");
          return (
            <div key={c.label} className="rounded-xl border border-border/70 bg-surface/40 p-4">
              <div className="flex items-center gap-1.5 text-xs text-ink-faint"><Ic className="size-4" /> {c.label}</div>
              <p className={`mt-2 text-2xl font-semibold tabular-nums ${isScore ? scoreColor : "text-ink"}`}>{c.value}</p>
            </div>
          );
        })}
        <div className="rounded-xl border border-border/70 bg-surface/40 p-4">
          <div className="flex items-center gap-1.5 text-xs text-ink-faint"><FileText className="size-4" /> Wiki</div>
          <p className="mt-2 text-sm font-medium text-ink">{s.has_wiki ? t("kb.ovWiki") : t("kb.ovWikiNo")}</p>
        </div>
      </div>

      <div className="rounded-xl border border-border/70 bg-surface/40 p-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-ink">{t("kb.ovIssues")}</h3>
          <button onClick={onRetry} className="rounded p-1 text-ink-faint transition hover:text-ink" title={t("common.retry")}><ArrowsClockwise className="size-3.5" /></button>
        </div>
        {lint.issues.length === 0 ? (
          <p className="mt-3 text-[13px] text-ink-secondary">{t("kb.ovNoIssues")}</p>
        ) : (
          <ul className="mt-3 space-y-2">
            {lint.issues.map((iss, i) => (
              <li key={i} className="flex items-start gap-2 text-[13px]">
                <span className={`mt-0.5 size-1.5 shrink-0 rounded-full ${iss.level === "warn" || iss.level === "error" ? "bg-danger" : "bg-accent"}`} />
                <span className="text-ink-secondary">{iss.msg}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
