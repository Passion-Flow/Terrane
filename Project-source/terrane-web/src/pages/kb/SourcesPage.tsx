/** Sources subpage — source list (tiered upload fast/standard/high, parse-status polling, reparse, type-to-confirm delete).
 *  The core content of the default landing page. */

import {
  ArrowsClockwise, CircleNotch, Eye, FileText, FunnelSimple, MagnifyingGlass, Plus, Trash,
  UploadSimple, WarningCircle,
} from "@phosphor-icons/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";

import { Modal } from "@/components/ui/Modal";
import { Select } from "@/components/ui/Select";
import { useKb } from "@/components/KbLayout";
import { ApiError } from "@/lib/api";
import {
  addSource, deleteSource, reparseSource, uploadSourceFile,
  type KbSource, type ParseTier,
} from "@/lib/kb";

const TIERS: ParseTier[] = ["fast", "standard", "high"];
const POLL_MS = 2500;
const PARSING = new Set(["pending", "parsing"]);

export function SourcesPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { id, seg, sources, reloadSources, canEdit } = useKb();

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

  // Polling: while any source is pending/parsing, refresh the source list every ~2.5s
  const hasParsing = useMemo(() => sources.some((s) => PARSING.has(s.status)), [sources]);
  useEffect(() => {
    if (!hasParsing) return;
    const h = window.setInterval(() => { void reloadSources(); }, POLL_MS);
    return () => clearInterval(h);
  }, [hasParsing, reloadSources]);

  async function onAdd() {
    if (!title.trim() || !text.trim() || busy) return;
    setBusy(true); setErr("");
    try {
      await addSource(id, { title: title.trim(), text });
      setOpen(false); setTitle(""); setText("");
      await reloadSources();
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
      await reloadSources();
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
      await reloadSources();
    } catch { /* ignore */ }
    finally { setReparsing(false); }
  }

  async function onDeleteSource() {
    if (!delFor) return;
    try { await deleteSource(id, delFor.id); setDelFor(null); setDelInput(""); await reloadSources(); } catch { /* ignore */ }
  }
  const onPreview = useCallback((s: KbSource) => { navigate(`/${seg}/kb/${id}/source/${s.id}`); }, [navigate, seg, id]);

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

  return (
    <div className="px-6 py-8 sm:px-8">
      <div className="mx-auto max-w-5xl">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-ink">{t("kbNav.sources")} <span className="text-lg font-normal text-ink-faint">({sources.length})</span></h1>
            <p className="mt-1 text-sm text-ink-secondary">{t("kbPages.sourcesSubtitle")}</p>
          </div>
          {canEdit && (
            <div className="flex shrink-0 items-center gap-2">
              <button onClick={() => { setUploadOpen(true); setErr(""); setTier("standard"); }} title={t("kb.uploadFile")}
                className="flex items-center gap-1.5 rounded-(--radius-control) border border-border px-3 py-1.5 text-sm font-medium text-ink-secondary transition hover:bg-canvas hover:text-ink">
                <UploadSimple className="size-4" /> {t("kb.upload")}
              </button>
              <button onClick={() => { setOpen(true); setErr(""); }} title={t("kb.addText")}
                className="flex items-center gap-1.5 rounded-(--radius-control) bg-accent px-3 py-1.5 text-sm font-medium text-white transition hover:bg-accent-hover">
                <Plus className="size-4" /> {t("kb.addText")}
              </button>
            </div>
          )}
        </div>

        {sources.length > 4 && (
          <div className="mt-5 flex items-center gap-1.5">
            <div className="relative flex-1">
              <MagnifyingGlass className="absolute start-3 top-1/2 size-4 -translate-y-1/2 text-ink-faint" />
              <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder={t("kb.sourceSearchPlaceholder")}
                className={`${field} ps-9`} />
            </div>
            <button onClick={() => setSort((s) => (s === "newest" ? "oldest" : "newest"))}
              title={t(sort === "newest" ? "common.sortNewest" : "common.sortOldest")}
              className="flex shrink-0 items-center gap-1 rounded-(--radius-control) border border-border px-3 py-2 text-sm text-ink-secondary transition hover:bg-canvas hover:text-ink">
              <FunnelSimple className="size-4" />
            </button>
          </div>
        )}

        <div className="mt-5 space-y-2">
          {sources.length === 0 ? (
            <div className="flex flex-col items-center rounded-(--radius-card) border border-dashed border-border bg-surface/30 py-16 text-center">
              <FileText className="size-8 text-ink-faint" />
              <p className="mt-3 text-sm text-ink-secondary">{t("kb.noSources")}</p>
            </div>
          ) : visibleSources.length === 0 ? (
            <p className="py-10 text-center text-sm text-ink-faint">{t("kb.noMatch")}</p>
          ) : visibleSources.map((s) => {
            const parsing = PARSING.has(s.status);
            const failed = s.status === "failed";
            return (
              <div key={s.id} className="group/src rounded-(--radius-control) border border-border/60 bg-surface/40 px-4 py-3 transition hover:border-border">
                <div className="flex items-start gap-3">
                  {parsing
                    ? <CircleNotch className="mt-0.5 size-4 shrink-0 animate-spin text-accent" />
                    : failed
                      ? <WarningCircle className="mt-0.5 size-4 shrink-0 text-danger" weight="fill" />
                      : <FileText className="mt-0.5 size-4 shrink-0 text-ink-faint" />}
                  <button onClick={() => onPreview(s)} title={t("kb.previewSource")} className="min-w-0 flex-1 text-start">
                    <p className="line-clamp-1 text-sm text-ink transition group-hover/src:text-accent">{s.title}</p>
                    <p className="mt-0.5 flex items-center gap-1 text-[11px]">
                      {parsing ? <span className="text-accent">{t("kb.statusParsing")}…</span>
                        : failed ? <span className="text-danger">{t("kb.statusFailed")}</span>
                          : <span className="text-ink-faint">{t("kb.chunks", { n: s.chunk_count })}</span>}
                    </p>
                  </button>
                  <div className="flex shrink-0 items-center gap-0.5">
                    <button onClick={() => onPreview(s)} title={t("kb.previewSource")}
                      className="rounded p-1.5 text-ink-faint opacity-0 transition hover:bg-accent-soft hover:text-accent group-hover/src:opacity-100">
                      <Eye className="size-4" />
                    </button>
                    {canEdit && (
                      <button onClick={() => { setDelFor(s); setDelInput(""); }} title={t("kb.deleteSource")}
                        className="rounded p-1.5 text-ink-faint opacity-0 transition hover:bg-danger-soft hover:text-danger group-hover/src:opacity-100">
                        <Trash className="size-4" />
                      </button>
                    )}
                  </div>
                </div>
                {failed && canEdit && (
                  <button onClick={() => { setReparseFor(s); setReparseTier("high"); }}
                    className="mt-2 flex w-full items-center justify-center gap-1 rounded-(--radius-control) border border-danger/30 bg-danger-soft py-1.5 text-xs font-medium text-danger transition hover:bg-danger-soft/70">
                    <ArrowsClockwise className="size-3.5" /> {t("kb.reparse")}
                  </button>
                )}
              </div>
            );
          })}
        </div>
      </div>

      <input ref={fileRef} type="file" hidden accept=".txt,.md,.markdown,.csv,.json,.log,.pdf,.docx,.xlsx,.pptx,.mp4,.mov,.avi,.webm,.mkv,text/*,video/*" onChange={onFile} />

      {/* Upload — choose parse tier */}
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

      {/* Reparse */}
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

      {/* Delete source — type-to-confirm */}
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

      {/* Add text */}
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
