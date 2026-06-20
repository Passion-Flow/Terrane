/** 记忆 —— per-user 个人记忆:自动记忆(从聊天/上传文档抽取)+ 手动添加 + 语义唤回 + 删除。 */

import { Brain, ChatCircleText, FileText, MagnifyingGlass, PencilSimple, Plus, Trash } from "@phosphor-icons/react";
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  addMemory, deleteMemory, getMemorySettings, listMemories, recallMemories, setMemorySettings,
  type Memory, type MemoryHit,
} from "@/lib/memory";

type SrcKey = "all" | "manual" | "chat" | "document";

export function MemoryPage() {
  const { t } = useTranslation();
  const [items, setItems] = useState<Memory[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<MemoryHit[] | null>(null);
  const [auto, setAuto] = useState(true);
  const [filter, setFilter] = useState<SrcKey>("all");

  const KIND_LABEL: Record<string, string> = {
    fact: t("memory.kindFact"), preference: t("memory.kindPref"), event: t("memory.kindEvent"),
  };
  const SRC: Record<string, { label: string; icon: typeof FileText; cls: string }> = {
    manual: { label: t("memory.srcManual"), icon: PencilSimple, cls: "bg-surface text-ink-secondary ring-border" },
    extracted: { label: t("memory.srcManual"), icon: PencilSimple, cls: "bg-surface text-ink-secondary ring-border" },
    chat: { label: t("memory.srcChat"), icon: ChatCircleText, cls: "bg-accent-soft text-accent ring-accent/30" },
    document: { label: t("memory.srcDocument"), icon: FileText, cls: "bg-success/10 text-success ring-success/30" },
  };

  const load = useCallback(async () => { setItems((await listMemories()).items); }, []);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => { getMemorySettings().then((r) => setAuto(r.auto)).catch(() => {}); }, []);

  async function toggleAuto() {
    const next = !auto;
    setAuto(next);
    try { await setMemorySettings(next); } catch { setAuto(!next); }
  }
  async function onAdd() {
    if (!input.trim() || busy) return;
    setBusy(true);
    try { await addMemory(input.trim()); setInput(""); await load(); } finally { setBusy(false); }
  }
  async function onRecall(e?: React.FormEvent) {
    e?.preventDefault();
    if (!q.trim()) { setHits(null); return; }
    setHits((await recallMemories(q.trim())).hits);
  }
  async function onDelete(id: string) {
    try { await deleteMemory(id); await load(); if (hits) await onRecall(); } catch { /* */ }
  }

  const field = "w-full rounded-(--radius-control) border border-border bg-canvas px-3 py-2 text-sm text-ink outline-none focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/30";
  const shown = items.filter((m) => filter === "all" || m.source === filter || (filter === "manual" && m.source === "extracted"));
  const counts = { chat: items.filter((m) => m.source === "chat").length, document: items.filter((m) => m.source === "document").length };

  return (
    <div className="px-8 py-10">
      <div className="mx-auto max-w-3xl">
        <h1 className="text-2xl font-bold tracking-tight text-ink">{t("memory.title")}</h1>
        <p className="mt-1.5 text-sm text-ink-secondary">{t("memory.subtitle")}</p>

        {/* 自动记忆开关 */}
        <div className="mt-5 flex items-start justify-between gap-4 rounded-xl border border-border/70 bg-surface/40 p-4">
          <div className="min-w-0">
            <p className="text-sm font-medium text-ink">{t("memory.autoTitle")}</p>
            <p className="mt-0.5 text-[13px] text-ink-secondary">{t("memory.autoHint")}</p>
            {(counts.chat > 0 || counts.document > 0) && (
              <p className="mt-1 text-[12px] text-ink-faint">{t("memory.autoStats", { chat: counts.chat, doc: counts.document })}</p>
            )}
          </div>
          <button onClick={toggleAuto} role="switch" aria-checked={auto}
            className={`relative mt-0.5 h-6 w-11 shrink-0 rounded-full transition ${auto ? "bg-accent" : "bg-border"}`}>
            <span className={`absolute top-0.5 size-5 rounded-full bg-white shadow transition-all ${auto ? "start-[22px]" : "start-0.5"}`} />
          </button>
        </div>

        {/* 手动添加 */}
        <div className="mt-4 flex items-center gap-2">
          <input value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => e.key === "Enter" && onAdd()}
            placeholder={t("memory.addPlaceholder")} disabled={busy} className={field} />
          <button onClick={onAdd} disabled={busy || !input.trim()}
            className="flex shrink-0 items-center gap-1 rounded-(--radius-control) bg-accent px-3.5 py-2 text-sm font-medium text-white transition active:translate-y-px hover:bg-accent-hover disabled:opacity-50">
            <Plus className="size-4" /> {t("memory.add")}
          </button>
        </div>

        <form onSubmit={onRecall} className="mt-3 relative">
          <MagnifyingGlass className="absolute start-3 top-1/2 size-4 -translate-y-1/2 text-ink-faint" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("memory.recallPlaceholder")} className={`${field} ps-9`} />
        </form>

        {/* 来源筛选 */}
        <div className="mt-5 flex flex-wrap gap-1.5">
          {(["all", "manual", "chat", "document"] as SrcKey[]).map((k) => (
            <button key={k} onClick={() => setFilter(k)}
              className={`rounded-full border px-2.5 py-1 text-[12px] font-medium transition ${filter === k ? "border-accent bg-accent-soft text-accent" : "border-border text-ink-secondary hover:bg-surface"}`}>
              {t(`memory.filter.${k}`)}
            </button>
          ))}
        </div>

        <div className="mt-4 space-y-2">
          {hits !== null && (
            <div className="mb-4 rounded-xl border border-accent/30 bg-accent-soft/40 p-3">
              <p className="mb-2 text-xs font-medium text-accent">{t("memory.recallResult", { n: hits.length })}</p>
              {hits.map((h) => (
                <div key={h.id} className="flex items-center justify-between py-1 text-[13px]">
                  <span className="text-ink">{h.content}</span>
                  <span className="text-xs text-ink-faint">{h.score}</span>
                </div>
              ))}
            </div>
          )}
          {shown.length === 0 ? (
            <div className="flex flex-col items-center py-16 text-center">
              <Brain className="size-9 text-ink-faint" />
              <p className="mt-3 text-sm text-ink-secondary">{t("memory.empty")}</p>
            </div>
          ) : shown.map((m) => {
            const s = SRC[m.source] ?? SRC.manual;
            const Si = s.icon;
            return (
              <div key={m.id} className="group/m flex items-center justify-between gap-3 rounded-(--radius-control) border border-border/60 bg-surface/40 px-4 py-2.5">
                <span className="flex min-w-0 items-center gap-2 text-[13px] text-ink">
                  <span className={`inline-flex shrink-0 items-center gap-1 rounded px-1.5 py-0.5 text-[11px] ring-1 ${s.cls}`}>
                    <Si className="size-3" /> {s.label}
                  </span>
                  <span className="shrink-0 rounded bg-canvas px-1.5 py-0.5 text-[11px] text-ink-faint">{KIND_LABEL[m.kind] ?? m.kind}</span>
                  <span className="truncate">{m.content}</span>
                </span>
                <button onClick={() => onDelete(m.id)} className="shrink-0 rounded p-1 text-ink-faint opacity-0 transition hover:text-danger group-hover/m:opacity-100">
                  <Trash className="size-3.5" />
                </button>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
