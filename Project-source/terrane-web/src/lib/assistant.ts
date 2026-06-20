/** 个人 AI 助手 API —— 跨库检索+记忆+持久化对话。SSE 流式。 */

import { request } from "@/lib/api";
import { apiBase } from "@/lib/config";
import { getModelPref } from "@/lib/models";

export interface ConvItem { id: string; title: string; updated_at: string | null }
export interface AssistSource { n: number; source_title: string; kb: string; content: string }
export interface WebSource { index: number; title: string; url: string; site?: string }
export interface AttMeta { name: string; mime: string; thumb?: string }
export interface ChatMessage {
  role: "user" | "assistant"; content: string;
  sources?: AssistSource[]; webSources?: WebSource[]; attachments?: AttMeta[];
}

export const listConversations = () =>
  request<{ items: ConvItem[] }>("/api/v1/assistant/conversations", { credentials: "include" });

interface RawMsg { role: "user" | "assistant"; content: string; sources?: AssistSource[]; web_sources?: WebSource[]; attachments?: AttMeta[] }
export const getConversation = async (id: string): Promise<{ id: string; title: string; messages: ChatMessage[] }> => {
  const r = await request<{ id: string; title: string; messages: RawMsg[] }>(`/api/v1/assistant/conversations/${id}`, { credentials: "include" });
  return { ...r, messages: r.messages.map((m) => ({ role: m.role, content: m.content, sources: m.sources, webSources: m.web_sources, attachments: m.attachments })) };
};

export const deleteConversation = (id: string) =>
  request<{ ok: boolean }>(`/api/v1/assistant/conversations/${id}`, { method: "DELETE", credentials: "include" });

export interface AssistHandlers {
  onMeta?: (conversationId: string) => void;
  onSources?: (hits: AssistSource[]) => void;
  onWebSources?: (results: WebSource[]) => void;
  onDelta?: (text: string) => void;
  onError?: (e: { code?: string; message?: string }) => void;
  onDone?: () => void;
}

export interface Attachment { name: string; mime: string; data: string }

export interface AssistOptions {
  conversationId?: string | null;
  attachments?: Attachment[];
  attMeta?: AttMeta[];
  useKb?: boolean;
  kbIds?: string[];
  webSearch?: boolean;
}

export async function streamAssistant(query: string, opts: AssistOptions, h: AssistHandlers, signal?: AbortSignal): Promise<void> {
  const resp = await fetch(`${apiBase()}/api/v1/assistant/chat`, {
    method: "POST", credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query, conversation_id: opts.conversationId || undefined,
      model: getModelPref("chat") || undefined,
      embed_model: getModelPref("embed") || undefined,
      rerank_model: getModelPref("rerank") || undefined,
      attachments: opts.attachments || [],
      att_meta: opts.attMeta || [],
      use_kb: opts.useKb || false,
      kb_ids: opts.kbIds || [],
      web_search: opts.webSearch || false,
    }),
    signal,
  });
  if (!resp.ok || !resp.body) { h.onError?.({ code: "HTTP_" + resp.status }); return; }
  const reader = resp.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const blocks = buf.split("\n\n");
    buf = blocks.pop() ?? "";
    for (const blk of blocks) {
      let ev = "message"; let data = "";
      for (const line of blk.split("\n")) {
        if (line.startsWith("event:")) ev = line.slice(6).trim();
        else if (line.startsWith("data:")) data = line.slice(5).trim();
      }
      if (!data) continue;
      let p: Record<string, unknown>;
      try { p = JSON.parse(data); } catch { continue; }
      if (ev === "meta") h.onMeta?.(p.conversation_id as string);
      else if (ev === "sources") h.onSources?.(p.hits as AssistSource[]);
      else if (ev === "web_sources") h.onWebSources?.(p.results as WebSource[]);
      else if (ev === "delta") h.onDelta?.(p.text as string);
      else if (ev === "error") h.onError?.(p as { code?: string; message?: string });
      else if (ev === "done") h.onDone?.();
    }
  }
}
