/** Knowledge base RAG Q&A panel — streaming answers + clickable cited sources + typing animation + clear history. */

import { ArrowClockwise, ChatCircleText, FileText, PaperPlaneRight, Trash } from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router";

import { Markdown } from "@/components/ui/Markdown";
import { FALLBACK_LANG, isSupported } from "@/i18n/langs";
import { streamChat, verifyAnswer, type ChatSource } from "@/lib/kb";

interface Msg { role: "user" | "assistant"; content: string; sources?: ChatSource[]; error?: string; grounded?: number | null }

export function KbChat({ kbId }: { kbId: string }) {
  const { t } = useTranslation();
  const { lang } = useParams();
  const navigate = useNavigate();
  const seg = lang && isSupported(lang) ? lang : FALLBACK_LANG;
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs]);

  function patchLast(fn: (m: Msg) => Msg) {
    setMsgs((prev) => { const c = [...prev]; c[c.length - 1] = fn(c[c.length - 1]); return c; });
  }

  function openSource(s: ChatSource) {
    navigate(`/${seg}/kb/${kbId}/source/${s.source_id}`);
  }

  async function send(text?: string) {
    const q = (text ?? input).trim();
    if (!q || busy) return;
    setInput(""); setBusy(true);
    setMsgs((m) => [...m, { role: "user", content: q }, { role: "assistant", content: "", sources: [] }]);
    let acc = ""; let srcs: ChatSource[] = [];
    try {
      await streamChat(kbId, q, {
        onSources: (hits) => { srcs = hits; patchLast((m) => ({ ...m, sources: hits })); },
        onDelta: (txt) => { acc += txt; patchLast((m) => ({ ...m, content: m.content + txt })); },
        onError: (e) => patchLast((m) => ({ ...m, error: e.code === "NO_CHAT_CHANNEL" ? t("kb.noChatModel") : t("kb.chatError") })),
        onDone: () => setBusy(false),
      });
      // Self-developed answer-grounding check (engine 4): verify the answer against its cited sources.
      if (acc.trim() && srcs.length) {
        try {
          const v = await verifyAnswer(kbId, acc, srcs.map((s) => s.content));
          patchLast((m) => ({ ...m, grounded: v.grounded }));
        } catch { /* verification is best-effort */ }
      }
    } catch { patchLast((m) => ({ ...m, error: t("kb.chatError") })); }
    finally { setBusy(false); }
  }

  const examples = t("kb.chatExamples", { returnObjects: true }) as string[];

  return (
    <div className="flex h-full min-h-0 flex-col rounded-xl border border-border/70 bg-surface/40">
      {msgs.length > 0 && (
        <div className="flex items-center justify-end border-b border-border/50 px-3 py-1.5">
          <button onClick={() => { if (!busy) setMsgs([]); }} disabled={busy}
            className="flex items-center gap-1 rounded-full px-2 py-1 text-[11px] text-ink-faint transition hover:bg-canvas hover:text-ink disabled:opacity-40">
            <Trash className="size-3" /> {t("kb.clearChat")}
          </button>
        </div>
      )}
      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4">
        {msgs.length === 0 && (
          <div className="flex flex-1 flex-col items-center justify-center gap-4 px-4 text-center">
            <span className="flex size-14 items-center justify-center rounded-full bg-accent-soft text-accent">
              <ChatCircleText className="size-7" weight="duotone" />
            </span>
            <p className="max-w-sm text-sm text-ink-secondary">{t("kb.chatHint")}</p>
            {Array.isArray(examples) && examples.length > 0 && (
              <div className="flex max-w-md flex-wrap justify-center gap-2">
                {examples.map((ex) => (
                  <button key={ex} type="button" onClick={() => void send(ex)}
                    className="rounded-full border border-border bg-canvas px-3 py-1.5 text-[12px] text-ink-secondary transition hover:border-accent hover:text-accent">
                    {ex}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
        {msgs.map((m, i) => {
          const isLast = i === msgs.length - 1;
          const streaming = m.role === "assistant" && busy && isLast;
          return (
            <div key={i} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
              <div className={m.role === "user"
                ? "max-w-[80%] rounded-2xl rounded-ee-sm bg-accent px-3.5 py-2 text-[13px] text-white"
                : "max-w-[85%] rounded-2xl rounded-es-sm bg-surface px-3.5 py-2.5 text-[13px] text-ink ring-1 ring-border/60"}>
                {m.role === "user" ? (
                  <p className="whitespace-pre-wrap leading-relaxed">{m.content}</p>
                ) : (
                  <>
                    {m.sources && m.sources.length > 0 && (
                      <div className="mb-2 border-b border-border/40 pb-2">
                        <p className="mb-1.5 text-[10px] font-medium uppercase tracking-wide text-ink-faint">{t("kb.citedSources")}</p>
                        <div className="flex flex-wrap gap-1.5">
                          {m.sources.map((s) => {
                            const path = (s.citation_path || []).filter(Boolean);
                            const pages = s.page_start ? (s.page_end && s.page_end !== s.page_start ? ` p.${s.page_start}–${s.page_end}` : ` p.${s.page_start}`) : "";
                            const label = path.length > 1 ? path.slice(1).join(" › ") + pages : s.source_title + pages;
                            return (
                              <button key={s.n} title={`${t("kb.openSource")} · ${path.join(" › ") || s.source_title}${pages}\n${s.content.slice(0, 120)}`} onClick={() => openSource(s)}
                                className="inline-flex max-w-full items-center gap-1 rounded-full bg-accent-soft px-2 py-0.5 text-[11px] text-accent transition hover:bg-accent hover:text-white">
                                <FileText className="size-3 shrink-0" /> <span className="truncate">[{s.n}] {label}</span>
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    )}
                    {m.content
                      ? <Markdown>{m.content}</Markdown>
                      : streaming && (
                        <span className="inline-flex items-center gap-1 py-1">
                          <span className="size-1.5 animate-bounce rounded-full bg-ink-faint [animation-delay:-0.3s]" />
                          <span className="size-1.5 animate-bounce rounded-full bg-ink-faint [animation-delay:-0.15s]" />
                          <span className="size-1.5 animate-bounce rounded-full bg-ink-faint" />
                        </span>
                      )}
                    {m.content && streaming && <span className="ms-0.5 inline-block w-1 animate-pulse">▋</span>}
                    {m.error && (
                      <p className="mt-1 flex items-center gap-1 text-[12px] text-danger"><ArrowClockwise className="size-3" /> {m.error}</p>
                    )}
                    {typeof m.grounded === "number" && (
                      <span title={t("kb.groundedHint")}
                        className={`mt-1.5 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium ${
                          m.grounded >= 0.8 ? "bg-emerald-500/12 text-emerald-600"
                            : m.grounded >= 0.5 ? "bg-amber-500/12 text-amber-600" : "bg-danger/12 text-danger"}`}>
                        {t("kb.grounded")} {Math.round(m.grounded * 100)}%
                      </span>
                    )}
                  </>
                )}
              </div>
            </div>
          );
        })}
        <div ref={endRef} />
      </div>
      <div className="border-t border-border/60 p-3">
        <form onSubmit={(e) => { e.preventDefault(); void send(); }} className="flex items-center gap-2">
          <input value={input} onChange={(e) => setInput(e.target.value)} disabled={busy} placeholder={t("kb.chatPlaceholder")}
            className="flex-1 rounded-full border border-border bg-canvas px-4 py-2 text-sm text-ink outline-none focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/30" />
          <button type="submit" disabled={busy || !input.trim()}
            className="flex size-9 items-center justify-center rounded-full bg-accent text-white transition hover:bg-accent-hover disabled:opacity-50">
            <PaperPlaneRight className="size-4" weight="fill" />
          </button>
        </form>
      </div>
    </div>
  );
}
