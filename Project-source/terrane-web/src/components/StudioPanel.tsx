/** Studio panel (NotebookLM-style) — one-click generation of 8 artifact types + per-type rendering.
 *  taste-skill: single accent color, cards with real hierarchy only, skeleton screens (not spinners), empty states, :active micro-shift, label on top. */

import {
  ArrowLeft, Cards, ClockCounterClockwise, DownloadSimple, FileText, GraduationCap,
  ListChecks, Microphone, Presentation, Question, Sparkle, Table, TreeStructure, type Icon,
} from "@phosphor-icons/react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Markdown } from "@/components/ui/Markdown";
import {
  exportSlideDeck, generateAudioOverview, generateStudio,
  type DataTable, type Flashcard, type MindMap, type Podcast, type QuizItem,
  type SlideDeck, type StudioKind, type StudioResult,
} from "@/lib/studio";

const TILES: { kind: StudioKind; icon: Icon }[] = [
  { kind: "study_guide", icon: GraduationCap },
  { kind: "faq", icon: Question },
  { kind: "briefing", icon: FileText },
  { kind: "timeline", icon: ClockCounterClockwise },
  { kind: "mind_map", icon: TreeStructure },
  { kind: "flashcards", icon: Cards },
  { kind: "quiz", icon: ListChecks },
  { kind: "data_table", icon: Table },
  { kind: "slide_deck", icon: Presentation },
  { kind: "audio_overview", icon: Microphone },
];

function Flashcards({ cards }: { cards: Flashcard[] }) {
  const [flipped, setFlipped] = useState<Set<number>>(new Set());
  return (
    <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
      {cards.map((c, i) => (
        <button key={i} onClick={() => setFlipped((s) => { const n = new Set(s); n.has(i) ? n.delete(i) : n.add(i); return n; })}
          className="min-h-[5rem] rounded-xl border border-border/70 bg-surface/40 p-3.5 text-start text-[13px] transition active:translate-y-px hover:border-accent/40">
          <p className="text-[11px] uppercase tracking-wide text-ink-faint">{flipped.has(i) ? "A" : "Q"}</p>
          <p className="mt-1 text-ink">{flipped.has(i) ? c.back : c.front}</p>
        </button>
      ))}
    </div>
  );
}

function Quiz({ items }: { items: QuizItem[] }) {
  const [picked, setPicked] = useState<Record<number, number>>({});
  return (
    <div className="space-y-4">
      {items.map((q, qi) => (
        <div key={qi} className="rounded-xl border border-border/70 bg-surface/40 p-4">
          <p className="text-[13px] font-medium text-ink">{qi + 1}. {q.q}</p>
          <div className="mt-2 space-y-1.5">
            {q.options.map((opt, oi) => {
              const sel = picked[qi];
              const isAns = oi === q.answer;
              const show = sel !== undefined;
              return (
                <button key={oi} onClick={() => setPicked((p) => ({ ...p, [qi]: oi }))}
                  className={`block w-full rounded-(--radius-control) border px-3 py-1.5 text-start text-[13px] transition active:translate-y-px ${
                    show && isAns ? "border-accent bg-accent-soft text-accent"
                    : show && sel === oi ? "border-danger bg-danger-soft text-danger"
                    : "border-border/60 text-ink-secondary hover:bg-canvas"}`}>
                  {String.fromCharCode(65 + oi)}. {opt}
                </button>
              );
            })}
          </div>
          {picked[qi] !== undefined && q.explain && <p className="mt-2 text-xs text-ink-faint">{q.explain}</p>}
        </div>
      ))}
    </div>
  );
}

function MindMapView({ map }: { map: MindMap }) {
  const children = (pid: string) => map.nodes.filter((n) => n.parent === pid);
  const Branch = ({ pid, depth }: { pid: string; depth: number }) => (
    <ul className={depth ? "ms-4 border-s border-border/60 ps-3" : ""}>
      {children(pid).map((n) => (
        <li key={n.id} className="mt-1.5">
          <span className="text-[13px] text-ink">{n.label}</span>
          <Branch pid={n.id} depth={depth + 1} />
        </li>
      ))}
    </ul>
  );
  return (
    <div>
      <p className="mb-2 inline-block rounded-(--radius-control) bg-accent-soft px-2.5 py-1 text-sm font-medium text-accent">{map.root}</p>
      <Branch pid="root" depth={0} />
    </div>
  );
}

function TableView({ table }: { table: DataTable }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-border/70">
      <table className="w-full text-[13px]">
        <thead><tr className="border-b border-border/60 bg-surface/40">{table.columns.map((c, i) => <th key={i} className="px-3 py-2 text-start font-medium text-ink">{c}</th>)}</tr></thead>
        <tbody className="divide-y divide-border/50">
          {table.rows.map((r, ri) => <tr key={ri}>{r.map((cell, ci) => <td key={ci} className="px-3 py-2 text-ink-secondary">{cell}</td>)}</tr>)}
        </tbody>
      </table>
    </div>
  );
}

function SlideDeckView({ deck, kbId }: { deck: SlideDeck; kbId: string }) {
  const { t } = useTranslation();
  const [downloading, setDownloading] = useState(false);
  async function dl() { setDownloading(true); try { await exportSlideDeck(kbId); } catch { /* */ } finally { setDownloading(false); } }
  return (
    <div>
      <div className="mb-3 flex items-center justify-between gap-2">
        <p className="text-base font-semibold text-ink">{deck.title}{deck.subtitle && <span className="ms-2 text-sm font-normal text-ink-faint">{deck.subtitle}</span>}</p>
        <button onClick={dl} disabled={downloading}
          className="flex shrink-0 items-center gap-1.5 rounded-(--radius-control) bg-accent px-3 py-1.5 text-[13px] font-medium text-white transition active:translate-y-px hover:bg-accent-hover disabled:opacity-50">
          <DownloadSimple className="size-4" /> {downloading ? t("studio.exporting") : t("studio.downloadPptx")}
        </button>
      </div>
      <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
        {deck.slides?.map((s, i) => (
          <div key={i} className="rounded-xl border border-border/70 bg-canvas p-3.5">
            <p className="text-[11px] text-ink-faint">{i + 1}</p>
            <p className="mt-0.5 text-[13px] font-semibold text-ink">{s.title}</p>
            <ul className="mt-1.5 ms-4 list-disc space-y-1 text-[12px] text-ink-secondary">
              {s.bullets?.map((b, j) => <li key={j}>{b}</li>)}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}

function PodcastView({ pod }: { pod: Podcast }) {
  return (
    <div className="space-y-4">
      <audio controls src={pod.audio} className="w-full" />
      <div className="space-y-2">
        {pod.script?.map((l, i) => (
          <div key={i} className="flex gap-2 text-[13px]">
            <span className={`mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold ${l.speaker === "A" ? "bg-accent-soft text-accent" : "bg-surface text-ink-secondary ring-1 ring-border"}`}>{l.speaker}</span>
            <p className="leading-relaxed text-ink-secondary">{l.text}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

export function StudioPanel({ kbId }: { kbId: string }) {
  const { t } = useTranslation();
  const [active, setActive] = useState<StudioKind | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<StudioResult | null>(null);
  const [podcast, setPodcast] = useState<Podcast | null>(null);
  const [err, setErr] = useState("");

  async function run(kind: StudioKind) {
    setActive(kind); setLoading(true); setResult(null); setPodcast(null); setErr("");
    try {
      if (kind === "audio_overview") {
        const r = await generateAudioOverview(kbId);
        if (r.ok === false || !r.content) {
          setErr(r.reason === "no_sources" ? t("studio.noSources")
            : r.reason === "no_tts_channel" ? t("studio.noTts")
            : r.reason === "rate_limited" ? t("studio.rateLimited") : t("studio.failed"));
        } else setPodcast(r.content);
      } else {
        const r = await generateStudio(kbId, kind);
        if (r.ok === false || r.format === "empty") setErr(r.reason === "no_sources" ? t("studio.noSources") : t("studio.failed"));
        else setResult(r);
      }
    } catch { setErr(t("studio.failed")); }
    finally { setLoading(false); }
  }

  if (active) {
    return (
      <div className="rounded-xl border border-border/70 bg-surface/40 p-5">
        <div className="mb-3 flex items-center justify-between">
          <button onClick={() => { setActive(null); setResult(null); setErr(""); }} className="flex items-center gap-1 text-sm text-ink-secondary hover:text-ink">
            <ArrowLeft className="size-4" /> {t("studio.back")}
          </button>
          <span className="text-sm font-medium text-ink">{t(`studio.kind.${active}`)}</span>
        </div>
        {loading ? (
          <div className="space-y-2.5">
            {active === "audio_overview" && <p className="mb-3 text-[13px] text-ink-faint">{t("studio.synthHint")}</p>}
            {[...Array(6)].map((_, i) => <div key={i} className="h-4 animate-pulse rounded bg-canvas" style={{ width: `${90 - i * 8}%` }} />)}
          </div>
        ) : err ? (
          <p className="py-10 text-center text-sm text-ink-faint">{err}</p>
        ) : podcast ? (
          <PodcastView pod={podcast} />
        ) : result ? (
          <div>
            {result.kind === "slide_deck" ? <SlideDeckView deck={result.content as SlideDeck} kbId={kbId} />
              : result.format === "markdown" ? <Markdown>{String(result.content)}</Markdown>
              : null}
            {result.kind === "flashcards" && <Flashcards cards={result.content as Flashcard[]} />}
            {result.kind === "quiz" && <Quiz items={result.content as QuizItem[]} />}
            {result.kind === "mind_map" && <MindMapView map={result.content as MindMap} />}
            {result.kind === "data_table" && <TableView table={result.content as DataTable} />}
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-border/70 bg-surface/40 p-4">
      <div className="mb-3 flex items-center gap-1.5">
        <Sparkle className="size-4 text-accent" weight="fill" />
        <span className="text-sm font-medium text-ink">{t("studio.title")}</span>
      </div>
      <p className="mb-3 text-[13px] text-ink-secondary">{t("studio.subtitle")}</p>
      <div className="grid grid-cols-2 gap-2.5">
        {TILES.map(({ kind, icon: Ic }) => (
          <button key={kind} onClick={() => run(kind)}
            className="flex items-center gap-2 rounded-xl border border-border/70 bg-canvas px-3 py-3 text-start text-[13px] font-medium text-ink-secondary transition active:translate-y-px hover:border-accent/50 hover:text-ink">
            <Ic className="size-4.5 shrink-0 text-accent" /> {t(`studio.kind.${kind}`)}
          </button>
        ))}
      </div>
    </div>
  );
}
