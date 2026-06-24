/** 基于「单份文档」的 RAG 问答面板 —— 流式答案 + 引用来源。
 *  与 KbChat 同构,但调 streamChat(kbId, q, ..., sourceId) 仅在该文档范围内检索问答。 */

import { ChatCircleText, FileText, PaperPlaneRight } from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { streamChat, type ChatSource } from "@/lib/kb";

interface Msg { role: "user" | "assistant"; content: string; sources?: ChatSource[]; error?: string }

export function DocumentSourceChat({
  kbId, sourceId, onCite,
}: {
  kbId: string;
  sourceId: string;
  /** 点击引用 badge 的回调(可用于切到「解析对比」并滚动)。可选。 */
  onCite?: (s: ChatSource) => void;
}) {
  const { t } = useTranslation();
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs]);
  useEffect(() => () => abortRef.current?.abort(), []);

  function patchLast(fn: (m: Msg) => Msg) {
    setMsgs((prev) => { const c = [...prev]; c[c.length - 1] = fn(c[c.length - 1]); return c; });
  }

  async function send() {
    const q = input.trim();
    if (!q || busy) return;
    setInput(""); setBusy(true);
    setMsgs((m) => [...m, { role: "user", content: q }, { role: "assistant", content: "", sources: [] }]);
    const ac = new AbortController();
    abortRef.current = ac;
    try {
      await streamChat(kbId, q, {
        onSources: (hits) => patchLast((m) => ({ ...m, sources: hits })),
        onDelta: (txt) => patchLast((m) => ({ ...m, content: m.content + txt })),
        onError: (e) => patchLast((m) => ({ ...m, error: e.code === "NO_CHAT_CHANNEL" ? t("kb.noChatModel") : t("kb.chatError") })),
        onDone: () => setBusy(false),
      }, ac.signal, sourceId);
    } catch { patchLast((m) => ({ ...m, error: t("kb.chatError") })); }
    finally { setBusy(false); }
  }

  return (
    <div className="mx-auto flex h-full w-full max-w-3xl flex-col">
      <div className="flex-1 space-y-4 overflow-y-auto px-4 py-5">
        {msgs.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center gap-3 py-16 text-center">
            <span className="flex size-12 items-center justify-center rounded-full bg-accent-soft text-accent">
              <ChatCircleText className="size-6" weight="duotone" />
            </span>
            <p className="max-w-sm text-sm text-ink-faint">{t("source.askThisDocHint")}</p>
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
            <div className={m.role === "user"
              ? "max-w-[80%] rounded-2xl rounded-ee-sm bg-accent px-3.5 py-2 text-[13px] text-white"
              : "max-w-[85%] rounded-2xl rounded-es-sm bg-surface px-3.5 py-2.5 text-[13px] text-ink ring-1 ring-border/60"}>
              {m.role === "assistant" && m.sources && m.sources.length > 0 && (
                <div className="mb-2 flex flex-wrap gap-1.5 border-b border-border/40 pb-2">
                  {m.sources.map((s) => (
                    <button
                      key={s.n}
                      type="button"
                      title={s.content}
                      onClick={() => onCite?.(s)}
                      className="inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded bg-accent-soft px-1.5 py-0.5 text-[11px] text-accent transition hover:bg-accent/15"
                    >
                      <FileText className="size-3 shrink-0" /> [{s.n}] {s.source_title}
                    </button>
                  ))}
                </div>
              )}
              <p className="whitespace-pre-wrap leading-relaxed">{m.content}{m.role === "assistant" && busy && i === msgs.length - 1 && <span className="ms-0.5 animate-pulse">▋</span>}</p>
              {m.error && <p className="mt-1 text-[12px] text-danger">{m.error}</p>}
            </div>
          </div>
        ))}
        <div ref={endRef} />
      </div>
      <div className="border-t border-border/60 p-3">
        <form onSubmit={(e) => { e.preventDefault(); void send(); }} className="flex items-center gap-2">
          <input value={input} onChange={(e) => setInput(e.target.value)} disabled={busy} placeholder={t("source.askThisDocPlaceholder")}
            className="flex-1 rounded-full border border-border bg-canvas px-4 py-2 text-sm text-ink outline-none focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/30" />
          <button type="submit" disabled={busy || !input.trim()} title={t("source.send")}
            className="flex size-9 shrink-0 items-center justify-center rounded-full bg-accent text-white transition hover:bg-accent-hover disabled:opacity-50">
            <PaperPlaneRight className="size-4" weight="fill" />
          </button>
        </form>
      </div>
    </div>
  );
}
