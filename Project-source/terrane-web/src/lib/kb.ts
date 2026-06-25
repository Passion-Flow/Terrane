/** Knowledge base API (frontend /api/v1/knowledge-bases). Cookie auth → credentials:include. */

import { request } from "@/lib/api";
import { apiBase } from "@/lib/config";
import { getChatModelPref, getModelPref } from "@/lib/models";

export type Visibility = "private" | "shared" | "workspace";

export interface Kb {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  visibility: Visibility;
  status: string;
  my_role: "owner" | "editor" | "viewer" | null;
  is_owner: boolean;
  created_at: string | null;
}

export interface KbSource {
  id: string;
  title: string;
  kind: string;
  status: string;
  size_bytes: number;
  chunk_count: number;
  error: string | null;
  created_at: string | null;
}

export interface KbSourceDetail extends KbSource {
  mime: string | null;
  parsed_text: string;
  has_original: boolean;
  render_status?: string | null;
  page_count?: number;
}

export interface SourcePage { n: number; w: number; h: number }
export interface SourcePages { status: string; page_count: number; pages: SourcePage[] }

export interface SearchHit {
  chunk_id: string;
  content: string;
  ord: number;
  source_title: string;
  source_id: string;
  score: number;
}

const opt = (method: string, body?: unknown): RequestInit => ({
  method, credentials: "include",
  headers: body ? { "Content-Type": "application/json" } : {},
  ...(body ? { body: JSON.stringify(body) } : {}),
});

export const listKbs = () =>
  request<{ items: Kb[]; total: number }>("/api/v1/knowledge-bases", { credentials: "include" });

export const createKb = (input: { name: string; description?: string; visibility?: Visibility }) =>
  request<Kb>("/api/v1/knowledge-bases", opt("POST", input));

export const getKb = (id: string) =>
  request<Kb>(`/api/v1/knowledge-bases/${id}`, { credentials: "include" });

export const updateKb = (id: string, input: { name?: string; description?: string; visibility?: Visibility }) =>
  request<Kb>(`/api/v1/knowledge-bases/${id}`, opt("PATCH", input));

export const deleteKb = (id: string) =>
  request<{ ok: boolean }>(`/api/v1/knowledge-bases/${id}`, opt("DELETE"));

export const listSources = (kbId: string) =>
  request<{ items: KbSource[] }>(`/api/v1/knowledge-bases/${kbId}/sources`, { credentials: "include" });

export const addSource = (kbId: string, input: { title: string; text: string }) =>
  request<{ id: string; title: string; status: string; chunk_count: number }>(
    `/api/v1/knowledge-bases/${kbId}/sources`, opt("POST", input));

export interface KbMember {
  user_id: string;
  email: string;
  username: string | null;
  role: "owner" | "viewer" | "editor";
}

export const listMembers = (kbId: string) =>
  request<{ owner: KbMember | null; members: KbMember[] }>(
    `/api/v1/knowledge-bases/${kbId}/members`, { credentials: "include" });

export const addMember = (kbId: string, input: { email: string; role: "viewer" | "editor" }) =>
  request<KbMember>(`/api/v1/knowledge-bases/${kbId}/members`, opt("POST", input));

export const removeMember = (kbId: string, userId: string) =>
  request<{ ok: boolean }>(`/api/v1/knowledge-bases/${kbId}/members/${userId}`, opt("DELETE"));

export type ParseTier = "fast" | "standard" | "high";

export async function uploadSourceFile(
  kbId: string, file: File, tier: ParseTier = "standard",
): Promise<{ id?: string; title?: string; status?: string; chunk_count?: number; ok?: boolean; reason?: string }> {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("tier", tier);
  const resp = await fetch(`${apiBase()}/api/v1/knowledge-bases/${kbId}/sources/upload`, {
    method: "POST", credentials: "include", body: fd,
  });
  if (!resp.ok) throw new Error("upload_failed_" + resp.status);
  return resp.json();
}

/** Re-parse a source that failed or whose tier should change (form: tier); returns {id, status}. */
export async function reparseSource(
  kbId: string, sourceId: string, tier: ParseTier = "standard",
): Promise<{ id?: string; status?: string }> {
  const fd = new FormData();
  fd.append("tier", tier);
  const resp = await fetch(`${apiBase()}/api/v1/knowledge-bases/${kbId}/sources/${sourceId}/reparse`, {
    method: "POST", credentials: "include", body: fd,
  });
  if (!resp.ok) throw new Error("reparse_failed_" + resp.status);
  return resp.json();
}

export const getSource = (kbId: string, sourceId: string) =>
  request<KbSourceDetail>(`/api/v1/knowledge-bases/${kbId}/sources/${sourceId}`, { credentials: "include" });

/** Per-page layout image manifest (page number + pixel width/height of each page's WebP). */
export const getSourcePages = (kbId: string, sourceId: string) =>
  request<SourcePages>(`/api/v1/knowledge-bases/${kbId}/sources/${sourceId}/pages`, { credentials: "include" });

/** Single-page WebP layout image URL (same-origin with cookie, usable directly as <img src>). */
export const sourcePageUrl = (kbId: string, sourceId: string, n: number) =>
  `${apiBase()}/api/v1/knowledge-bases/${kbId}/sources/${sourceId}/page/${n}`;

/** Original file URL (usable directly as <img src> or as an <a href> download). */
export const sourceOriginalUrl = (kbId: string, sourceId: string) =>
  `${apiBase()}/api/v1/knowledge-bases/${kbId}/sources/${sourceId}/original`;

/** Fetch the original file and create a local blob URL (for rendering the source on the left: PDF iframe / image img). Remember to revoke when done. */
export async function fetchSourceOriginal(kbId: string, sourceId: string): Promise<string> {
  const resp = await fetch(`${apiBase()}/api/v1/knowledge-bases/${kbId}/sources/${sourceId}/original`, { credentials: "include" });
  if (!resp.ok) throw new Error("no original");
  return URL.createObjectURL(await resp.blob());
}

export const deleteSource = (kbId: string, sourceId: string) =>
  request<{ ok: boolean }>(`/api/v1/knowledge-bases/${kbId}/sources/${sourceId}`, opt("DELETE"));

export const searchKb = (kbId: string, q: string, sourceId?: string) => {
  const qs = new URLSearchParams({ q });
  if (getModelPref("embed")) qs.set("embed_model", getModelPref("embed"));
  if (getModelPref("rerank")) qs.set("rerank_model", getModelPref("rerank"));
  if (sourceId) qs.set("source_id", sourceId);
  return request<{ query: string; hits: SearchHit[]; total: number }>(
    `/api/v1/knowledge-bases/${kbId}/search?${qs}`, { credentials: "include" });
};

export interface McpKey { id: string; name: string; token_prefix: string; last_used_at: string | null; created_at: string | null }

export const createMcpKey = (kbId: string, name: string) =>
  request<{ id: string; name: string; token: string; token_prefix: string; mcp_url: string }>(
    `/api/v1/knowledge-bases/${kbId}/mcp-keys`, opt("POST", { name }));

export const listMcpKeys = (kbId: string) =>
  request<{ items: McpKey[] }>(`/api/v1/knowledge-bases/${kbId}/mcp-keys`, { credentials: "include" });

export const deleteMcpKey = (kbId: string, keyId: string) =>
  request<{ ok: boolean }>(`/api/v1/knowledge-bases/${kbId}/mcp-keys/${keyId}`, opt("DELETE"));

export interface GraphNode { id: string; name: string; etype: string }
export interface GraphEdge { source: string; target: string; type: string }

export const buildGraph = (kbId: string) =>
  request<{ job_id: string | null; status: string; total: number }>(
    `/api/v1/knowledge-bases/${kbId}/graph/build`, opt("POST"));

export const graphStatus = (kbId: string) =>
  request<{ status: string; progress: number; error?: string | null }>(
    `/api/v1/knowledge-bases/${kbId}/graph/status`, { credentials: "include" });

export const getGraph = (kbId: string) =>
  request<{ nodes: GraphNode[]; edges: GraphEdge[] }>(
    `/api/v1/knowledge-bases/${kbId}/graph`, { credentials: "include" });

export interface WikiPage {
  id: string; slug: string; title: string; body_md: string;
  source: string; status: string; inferred: boolean; updated_at: string | null;
}

export const compileWiki = (kbId: string) =>
  request<{ job_id: string | null; status: string } & Partial<WikiPage> & { ok?: boolean; reason?: string }>(
    `/api/v1/knowledge-bases/${kbId}/wiki/compile`, opt("POST"));

export const wikiStatus = (kbId: string) =>
  request<{ status: "none" | "running" | "done" | "failed"; progress: number; error?: string | null }>(
    `/api/v1/knowledge-bases/${kbId}/wiki/status`, { credentials: "include" });

export const getWikiPage = (kbId: string, slug: string) =>
  request<WikiPage>(`/api/v1/knowledge-bases/${kbId}/wiki/${slug}`, { credentials: "include" });

export interface KbStats {
  sources: number;
  failed_sources: number;
  chunks: number;
  embedded_chunks: number;
  graph_nodes: number;
  has_wiki: boolean;
}
export interface KbLintIssue { level: "info" | "warn" | "error"; code: string; msg: string }
export interface KbLint { score: number; stats: KbStats; issues: KbLintIssue[] }

/** KB health check / statistics (sources / chunks / embeddings / graph nodes + issue list + score). */
export const lintKb = (kbId: string) =>
  request<KbLint>(`/api/v1/knowledge-bases/${kbId}/lint`, { credentials: "include" });

export interface ChatSource { n: number; source_title: string; source_id: string; content: string; score: number }

export interface ChatHandlers {
  onSources?: (hits: ChatSource[]) => void;
  onDelta?: (text: string) => void;
  onError?: (e: { code?: string; message?: string }) => void;
  onDone?: () => void;
}

/** RAG streaming Q&A: consumes SSE (event: sources / delta / error / done).
 *  Pass sourceId → retrieve and answer based only on that document (document-level Q&A). */
export async function streamChat(kbId: string, query: string, h: ChatHandlers, signal?: AbortSignal, sourceId?: string): Promise<void> {
  const resp = await fetch(`${apiBase()}/api/v1/knowledge-bases/${kbId}/chat`, {
    method: "POST", credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, model: getChatModelPref() || undefined, ...(sourceId ? { source_id: sourceId } : {}) }), signal,
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
      let parsed: Record<string, unknown>;
      try { parsed = JSON.parse(data); } catch { continue; }
      if (ev === "sources") h.onSources?.(parsed.hits as ChatSource[]);
      else if (ev === "delta") h.onDelta?.(parsed.text as string);
      else if (ev === "error") h.onError?.(parsed as { code?: string; message?: string });
      else if (ev === "done") h.onDone?.();
    }
  }
}
