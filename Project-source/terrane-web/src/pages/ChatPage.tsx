/** 个人 AI 助手（Kimi 式)—— 自动跨全部知识库检索 + 记忆 + 持久化对话历史。左对话列表 + 主聊天区。 */
import { Books, ChatCircleText, FileText, GlobeSimple, Paperclip, PaperPlaneRight, Plus, Sparkle, Trash, X } from "@phosphor-icons/react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { Select } from "@/components/ui/Select";
import {
  deleteConversation, getConversation, listConversations, streamAssistant,
  type AssistSource, type Attachment, type ChatMessage, type ConvItem,
} from "@/lib/assistant";
import { listKbs, type Kb } from "@/lib/kb";
import { getModelPref, getModels, setModelPref, type ModelOption } from "@/lib/models";

function readFile(f: File): Promise<Attachment> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve({ name: f.name, mime: f.type || "application/octet-stream", data: String(r.result) });
    r.onerror = () => reject(new Error("read failed"));
    r.readAsDataURL(f);
  });
}

/** 图片 data URL → 小缩略图(最长边 96px,jpeg) */
function thumbFromDataUrl(dataUrl: string): Promise<string | undefined> {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => {
      const max = 96, scale = Math.min(1, max / Math.max(img.width, img.height));
      const c = document.createElement("canvas");
      c.width = Math.max(1, Math.round(img.width * scale));
      c.height = Math.max(1, Math.round(img.height * scale));
      const ctx = c.getContext("2d");
      if (!ctx) return resolve(undefined);
      ctx.drawImage(img, 0, 0, c.width, c.height);
      resolve(c.toDataURL("image/jpeg", 0.6));
    };
    img.onerror = () => resolve(undefined);
    img.src = dataUrl;
  });
}

export function ChatPage() {
  const { t } = useTranslation();
  const [convs, setConvs] = useState<ConvItem[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [msgs, setMsgs] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [atts, setAtts] = useState<Attachment[]>([]);
  const [useKb, setUseKb] = useState(false);
  const [webSearch, setWebSearch] = useState(false);
  const [kbId, setKbId] = useState("all");
  const [kbs, setKbs] = useState<Kb[]>([]);
  const [chatModels, setChatModels] = useState<ModelOption[]>([]);
  const [chatModel, setChatModel] = useState(getModelPref("chat"));
  const endRef = useRef<HTMLDivElement>(null);

  const loadConvs = useCallback(async () => { try { setConvs((await listConversations()).items); } catch { /* */ } }, []);
  useEffect(() => { void loadConvs(); }, [loadConvs]);
  useEffect(() => { listKbs().then((r) => setKbs(r.items)).catch(() => {}); }, []);
  useEffect(() => {
    getModels().then((r) => {
      const opts = r.data.chat ?? [];
      setChatModels(opts);
      setChatModel((cur) => cur || opts[0]?.model || "");
    }).catch(() => {});
  }, []);
  function pickModel(m: string) { setChatModel(m); setModelPref("chat", m); }
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs]);

  async function openConv(id: string) {
    setActiveId(id);
    try { setMsgs((await getConversation(id)).messages); } catch { setMsgs([]); }
  }
  function newChat() { setActiveId(null); setMsgs([]); setInput(""); }

  function patchLast(fn: (m: ChatMessage) => ChatMessage) {
    setMsgs((p) => { const c = [...p]; c[c.length - 1] = fn(c[c.length - 1]); return c; });
  }

  async function send() {
    const q = input.trim();
    if ((!q && atts.length === 0) || busy) return;
    const sending = atts;
    const attMeta = await Promise.all(sending.map(async (a) => ({
      name: a.name, mime: a.mime,
      thumb: a.mime.startsWith("image/") ? await thumbFromDataUrl(a.data) : undefined,
    })));
    setInput(""); setAtts([]); setBusy(true);
    setMsgs((m) => [...m, { role: "user", content: q, attachments: attMeta }, { role: "assistant", content: "", sources: [], webSources: [] }]);
    let convId = activeId;
    try {
      await streamAssistant(q || "(请基于附件回答)", {
        conversationId: activeId, attachments: sending, attMeta,
        useKb, kbIds: useKb && kbId !== "all" ? [kbId] : [], webSearch,
      }, {
        onMeta: (id) => { convId = id; setActiveId(id); },
        onSources: (hits: AssistSource[]) => patchLast((m) => ({ ...m, sources: hits })),
        onWebSources: (results) => patchLast((m) => ({ ...m, webSources: results })),
        onDelta: (txt) => patchLast((m) => ({ ...m, content: m.content + txt })),
        onError: (e) => patchLast((m) => ({ ...m, content: m.content || (e.code === "NO_CHAT_CHANNEL" ? t("assistant.noModel") : t("assistant.error")) })),
        onDone: () => {},
      });
    } catch { patchLast((m) => ({ ...m, content: m.content || t("assistant.error") })); }
    finally { setBusy(false); if (!activeId && convId) void loadConvs(); else void loadConvs(); }
  }

  async function delConv(id: string, e: React.MouseEvent) {
    e.stopPropagation();
    try { await deleteConversation(id); if (activeId === id) newChat(); await loadConvs(); } catch { /* */ }
  }

  return (
    <div className="flex h-full">
      {/* 对话列表 */}
      <div className="flex w-60 shrink-0 flex-col border-e border-border/70 bg-surface/30">
        <div className="p-3">
          <button onClick={newChat} className="flex w-full items-center gap-2 rounded-(--radius-control) border border-border bg-canvas px-3 py-2 text-sm font-medium text-ink transition active:translate-y-px hover:border-accent/50 hover:text-accent">
            <Plus className="size-4" weight="bold" /> {t("assistant.newChat")}
          </button>
        </div>
        <div className="flex-1 space-y-0.5 overflow-y-auto px-2 pb-3">
          {convs.length === 0 && <p className="px-2 py-6 text-center text-xs text-ink-faint">{t("assistant.noHistory")}</p>}
          {convs.map((c) => (
            <button key={c.id} onClick={() => openConv(c.id)}
              className={`group/c flex w-full items-center gap-2 rounded-(--radius-control) px-2.5 py-2 text-start text-[13px] transition ${activeId === c.id ? "bg-accent-soft text-accent" : "text-ink-secondary hover:bg-canvas hover:text-ink"}`}>
              <ChatCircleText className="size-4 shrink-0" />
              <span className="line-clamp-1 flex-1">{c.title}</span>
              <Trash onClick={(e) => delConv(c.id, e)} className="size-3.5 shrink-0 opacity-0 transition hover:text-danger group-hover/c:opacity-100" />
            </button>
          ))}
        </div>
      </div>

      {/* 聊天区 */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* 顶栏:模型快切 */}
        <div className="flex h-12 shrink-0 items-center justify-end gap-2 border-b border-border/60 px-4">
          <Sparkle className="size-3.5 text-ink-faint" />
          {chatModels.length > 0 ? (
            <Select size="sm" className="w-44" value={chatModel} onChange={pickModel}
              options={chatModels.map((m) => ({ value: m.model, label: m.name }))} />
          ) : (
            <span className="text-xs text-ink-faint">{t("assistant.noModel")}</span>
          )}
        </div>
        {msgs.length === 0 ? (
          <div className="flex flex-1 flex-col items-center justify-center px-6">
            <div className="flex size-14 items-center justify-center rounded-2xl bg-accent-soft"><Sparkle className="size-7 text-accent" weight="fill" /></div>
            <h2 className="mt-4 text-xl font-semibold tracking-tight text-ink">{t("assistant.welcome")}</h2>
            <p className="mt-1.5 text-sm text-ink-secondary">{t("assistant.welcomeSub")}</p>
            <div className="mt-6 w-full max-w-2xl"><Composer input={input} setInput={setInput} send={send} busy={busy} atts={atts} setAtts={setAtts} useKb={useKb} setUseKb={setUseKb} webSearch={webSearch} setWebSearch={setWebSearch} kbId={kbId} setKbId={setKbId} kbs={kbs} t={t} /></div>
          </div>
        ) : (
          <>
            <div className="flex-1 space-y-5 overflow-y-auto px-6 py-6">
              <div className="mx-auto max-w-3xl space-y-5">
                {msgs.map((m, i) => (
                  <div key={i} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
                    <div className={m.role === "user" ? "max-w-[80%] rounded-2xl rounded-ee-sm bg-accent px-4 py-2.5 text-sm text-white" : "max-w-[88%] text-sm text-ink"}>
                      {/* 用户气泡:附件缩略图 + 文件 chip */}
                      {m.role === "user" && m.attachments && m.attachments.length > 0 && (
                        <div className="mb-2 flex flex-wrap gap-1.5">
                          {m.attachments.map((a, j) => a.thumb ? (
                            <img key={j} src={a.thumb} alt={a.name} title={a.name} className="size-14 rounded-lg object-cover ring-1 ring-white/30" />
                          ) : (
                            <span key={j} title={a.name} className="inline-flex max-w-[12rem] items-center gap-1 rounded-md bg-white/15 px-2 py-1 text-[11px]">
                              <FileText className="size-3 shrink-0" /> <span className="truncate">{a.name}</span>
                            </span>
                          ))}
                        </div>
                      )}
                      {m.role === "assistant" && m.sources && m.sources.length > 0 && (
                        <div className="mb-2 flex flex-wrap gap-1.5">
                          {m.sources.map((s) => <span key={s.n} title={s.content} className="inline-flex items-center gap-1 rounded bg-accent-soft px-1.5 py-0.5 text-[11px] text-accent"><FileText className="size-3" /> [{s.n}] {s.kb}/{s.source_title}</span>)}
                        </div>
                      )}
                      <p className="whitespace-pre-wrap leading-relaxed">{m.content}{m.role === "assistant" && busy && i === msgs.length - 1 && <span className="ms-0.5 animate-pulse">▋</span>}</p>
                      {/* 助手气泡:联网来源卡片 */}
                      {m.role === "assistant" && m.webSources && m.webSources.length > 0 && (
                        <div className="mt-3 space-y-1.5">
                          <p className="text-[11px] font-medium text-ink-faint">{t("assistant.webSources")}</p>
                          <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
                            {m.webSources.slice(0, 6).map((s) => (
                              <a key={s.index} href={s.url} target="_blank" rel="noreferrer"
                                className="group flex items-start gap-2 rounded-lg border border-border bg-surface/40 px-2.5 py-1.5 transition hover:border-accent/50 hover:bg-accent-soft">
                                <span className="mt-0.5 flex size-4 shrink-0 items-center justify-center rounded bg-accent/15 text-[10px] font-semibold text-accent">{s.index}</span>
                                <span className="min-w-0">
                                  <span className="line-clamp-1 text-[12px] font-medium text-ink group-hover:text-accent">{s.title || s.url}</span>
                                  <span className="line-clamp-1 text-[10px] text-ink-faint">{s.site || s.url}</span>
                                </span>
                              </a>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
                <div ref={endRef} />
              </div>
            </div>
            <div className="border-t border-border/60 px-6 py-3"><div className="mx-auto max-w-3xl"><Composer input={input} setInput={setInput} send={send} busy={busy} atts={atts} setAtts={setAtts} useKb={useKb} setUseKb={setUseKb} webSearch={webSearch} setWebSearch={setWebSearch} kbId={kbId} setKbId={setKbId} kbs={kbs} t={t} /></div></div>
          </>
        )}
      </div>
    </div>
  );
}

function Composer({ input, setInput, send, busy, atts, setAtts, useKb, setUseKb, webSearch, setWebSearch, kbId, setKbId, kbs, t }: {
  input: string; setInput: (s: string) => void; send: () => void; busy: boolean;
  atts: Attachment[]; setAtts: React.Dispatch<React.SetStateAction<Attachment[]>>;
  useKb: boolean; setUseKb: (v: boolean) => void; webSearch: boolean; setWebSearch: (v: boolean) => void;
  kbId: string; setKbId: (v: string) => void; kbs: Kb[]; t: (k: string) => string;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  async function onPick(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []); e.target.value = "";
    const ok: Attachment[] = [];
    for (const f of files.slice(0, 5)) { if (f.size <= 60_000_000) { try { ok.push(await readFile(f)); } catch { /* */ } } }
    setAtts((a) => [...a, ...ok].slice(0, 5));
  }
  const pill = (on: boolean) => `flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[12px] font-medium transition active:translate-y-px ${on ? "border-accent bg-accent-soft text-accent" : "border-border text-ink-secondary hover:bg-surface hover:text-ink"}`;
  return (
    <div className="rounded-2xl border border-border bg-canvas p-2 shadow-sm transition focus-within:border-accent focus-within:ring-2 focus-within:ring-accent/30">
      {atts.length > 0 && (
        <div className="mb-1.5 flex flex-wrap gap-1.5 px-1">
          {atts.map((a, i) => (
            <span key={i} className="inline-flex items-center gap-1 rounded-md bg-surface px-2 py-1 text-[12px] text-ink-secondary ring-1 ring-border/60">
              <Paperclip className="size-3" /> <span className="max-w-[10rem] truncate">{a.name}</span>
              <button onClick={() => setAtts((p) => p.filter((_, j) => j !== i))} className="text-ink-faint hover:text-danger"><X className="size-3" /></button>
            </span>
          ))}
        </div>
      )}
      <textarea value={input} onChange={(e) => setInput(e.target.value)} rows={1}
        onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
        placeholder={t("assistant.placeholder")} disabled={busy}
        className="max-h-40 w-full resize-none bg-transparent px-2 py-1.5 text-sm text-ink outline-none placeholder:text-ink-faint" />
      <div className="flex items-center gap-1.5 px-1">
        <button onClick={() => fileRef.current?.click()} disabled={busy} title={t("assistant.attach")}
          className="flex size-8 shrink-0 items-center justify-center rounded-full text-ink-faint transition hover:bg-surface hover:text-ink disabled:opacity-40">
          <Plus className="size-5" />
        </button>
        <input ref={fileRef} type="file" hidden multiple accept=".txt,.md,.csv,.json,.pdf,.docx,.xlsx,.pptx,image/*,audio/*,video/*" onChange={onPick} />
        {/* 功能开关:默认全关 */}
        <button onClick={() => setUseKb(!useKb)} className={pill(useKb)} title={t("assistant.kbHint")}>
          <Books className="size-3.5" /> {t("assistant.kb")}
        </button>
        {useKb && kbs.length > 0 && (
          <Select size="sm" className="w-36" value={kbId} onChange={setKbId}
            options={[{ value: "all", label: t("assistant.allKb") }, ...kbs.map((k) => ({ value: k.id, label: k.name }))]} />
        )}
        <button onClick={() => setWebSearch(!webSearch)} className={pill(webSearch)} title={t("assistant.webHint")}>
          <GlobeSimple className="size-3.5" /> {t("assistant.web")}
        </button>
        <div className="flex-1" />
        <button onClick={send} disabled={busy || (!input.trim() && atts.length === 0)}
          className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-accent text-white transition active:translate-y-px hover:bg-accent-hover disabled:opacity-40">
          <PaperPlaneRight className="size-4" weight="fill" />
        </button>
      </div>
    </div>
  );
}
