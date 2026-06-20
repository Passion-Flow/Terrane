/** 知识库 RAG 问答面板 —— 流式答案 + 引用来源(知识复利的「带引用问答」)。 */

import { FileText, PaperPlaneRight } from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { streamChat, type ChatSource } from "@/lib/kb";

interface Msg { role: "user" | "assistant"; content: string; sources?: ChatSource[]; error?: string }

export function KbChat({ kbId }: { kbId: string }) {
  const { t } = useTranslation();
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs]);

  function patchLast(fn: (m: Msg) => Msg) {
    setMsgs((prev) => { const c = [...prev]; c[c.length - 1] = fn(c[c.length - 1]); return c; });
  }

  async function send() {
    const q = input.trim();
    if (!q || busy) return;
    setInput(""); setBusy(true);
    setMsgs((m) => [...m, { role: "user", content: q }, { role: "assistant", content: "", sources: [] }]);
    try {
      await streamChat(kbId, q, {
        onSources: (hits) => patchLast((m) => ({ ...m, sources: hits })),
        onDelta: (txt) => patchLast((m) => ({ ...m, content: m.content + txt })),
        onError: (e) => patchLast((m) => ({ ...m, error: e.code === "NO_CHAT_CHANNEL" ? t("kb.noChatModel") : t("kb.chatError") })),
        onDone: () => setBusy(false),
      });
    } catch { patchLast((m) => ({ ...m, error: t("kb.chatError") })); }
    finally { setBusy(false); }
  }

  return (
    <div className="flex h-[60vh] flex-col rounded-xl border border-border/70 bg-surface/40">
      <div className="flex-1 space-y-4 overflow-y-auto p-4">
        {msgs.length === 0 && (
          <p className="py-16 text-center text-sm text-ink-faint">{t("kb.chatHint")}</p>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
            <div className={m.role === "user"
              ? "max-w-[80%] rounded-2xl rounded-ee-sm bg-accent px-3.5 py-2 text-[13px] text-white"
              : "max-w-[85%] rounded-2xl rounded-es-sm bg-surface px-3.5 py-2.5 text-[13px] text-ink ring-1 ring-border/60"}>
              {m.role === "assistant" && m.sources && m.sources.length > 0 && (
                <div className="mb-2 flex flex-wrap gap-1.5 border-b border-border/40 pb-2">
                  {m.sources.map((s) => (
                    <span key={s.n} title={s.content} className="inline-flex items-center gap-1 rounded bg-accent-soft px-1.5 py-0.5 text-[11px] text-accent">
                      <FileText className="size-3" /> [{s.n}] {s.source_title}
                    </span>
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
