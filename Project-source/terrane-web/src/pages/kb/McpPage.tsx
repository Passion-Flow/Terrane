/** Connect subpage —— integrate this knowledge base with any external application:
 *  · MCP (Claude Code / Cursor)
 *  · Dify external knowledge base (/api/v1/external compatible endpoint)
 *  · Generic REST / OpenAPI (Coze plugins · GPTs Actions · n8n · FastGPT · custom direct integration)
 *  A single key (trn_ token) works across all integration methods. All copy actions go through CopyButton (works in non-secure HTTP contexts). */

import { Plus, Trash } from "@phosphor-icons/react";
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { useKb } from "@/components/KbLayout";
import { CopyButton } from "@/components/ui/CopyButton";
import { createMcpKey, deleteMcpKey, listMcpKeys, type McpKey } from "@/lib/kb";

type Tab = "mcp" | "dify" | "api";

export function McpPage() {
  const { t } = useTranslation();
  const { id } = useKb();
  const [keys, setKeys] = useState<McpKey[]>([]);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("mcp");

  const load = useCallback(async () => { try { setKeys((await listMcpKeys(id)).items); } catch { /* */ } }, [id]);
  useEffect(() => { void load(); }, [load]);

  // Automatically adapt scheme/host/port to the actual deployment —— origin already includes http(s) + IP/localhost/domain + non-default port
  const origin = window.location.origin;
  const mcpUrl = origin + "/mcp";
  const extBase = origin + "/api/v1/external";
  const tok = token ?? "<YOUR_TOKEN>";

  async function onCreate() {
    if (!name.trim() || busy) return;
    setBusy(true);
    try { const r = await createMcpKey(id, name.trim()); setToken(r.token); setName(""); await load(); }
    finally { setBusy(false); }
  }
  async function onDelete(k: McpKey) {
    if (!window.confirm(t("kb.mcpDeleteConfirm", { name: k.name }))) return;
    try { await deleteMcpKey(id, k.id); await load(); } catch { /* */ }
  }

  const mcpConfig = JSON.stringify(
    { mcpServers: { terrane: { url: mcpUrl, headers: { Authorization: `Bearer ${tok}` } } } }, null, 2);
  const curlSnippet = `curl -X POST ${extBase}/search \\\n  -H "Authorization: Bearer ${tok}" \\\n  -H "Content-Type: application/json" \\\n  -d '{"query": "your question", "top_k": 5}'`;

  const card = "rounded-(--radius-card) border border-border/70 bg-surface/40 p-5";
  const field = "w-full rounded-(--radius-control) border border-border bg-canvas px-3 py-2 text-sm text-ink outline-none focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/30";

  /** Single row: "label + copyable code". */
  const Row = ({ label, hint, value }: { label: string; hint?: string; value: string }) => (
    <div>
      <p className="text-[13px] font-medium text-ink">{label}</p>
      {hint && <p className="mt-0.5 text-[12px] leading-snug text-ink-faint">{hint}</p>}
      <div className="mt-1.5 flex items-center gap-2">
        <code className="flex-1 truncate rounded bg-canvas px-2.5 py-1.5 text-xs text-ink">{value}</code>
        <CopyButton value={value} title={t("kb.mcpCopy")} />
      </div>
    </div>
  );

  /** Code block + copy button in the top-right corner. */
  const Block = ({ value }: { value: string }) => (
    <div className="relative">
      <pre className="max-h-60 overflow-auto rounded-(--radius-control) bg-canvas p-3 pe-10 text-[11px] leading-relaxed text-ink-secondary">{value}</pre>
      <CopyButton value={value} title={t("kb.mcpCopy")}
        className="absolute end-2 top-2 rounded bg-surface p-1 text-ink-secondary hover:text-ink" iconClassName="size-3.5" />
    </div>
  );

  const TabBtn = ({ k, label }: { k: Tab; label: string }) => (
    <button onClick={() => setTab(k)}
      className={`shrink-0 whitespace-nowrap rounded-full px-3.5 py-1.5 text-[13px] font-medium transition ${
        tab === k ? "bg-accent text-white" : "text-ink-secondary hover:bg-canvas hover:text-ink"}`}>
      {label}
    </button>
  );

  return (
    <div className="px-6 py-8 sm:px-8">
      <div className="mx-auto max-w-3xl">
        <h1 className="text-2xl font-bold tracking-tight text-ink">{t("kb.connTitle")}</h1>
        <p className="mt-1 text-sm text-ink-secondary">{t("kb.connDesc")}</p>

        {/* Access keys */}
        <div className={`mt-6 ${card}`}>
          <p className="text-[13px] font-medium text-ink">{t("kb.connKeySection")}</p>
          <p className="mt-0.5 text-[12px] text-ink-faint">{t("kb.connKeyHint")}</p>

          {token && (
            <div className="mt-3 rounded-(--radius-control) border border-danger/30 bg-danger/5 p-3">
              <p className="text-[13px] font-medium text-danger">{t("kb.mcpTokenOnce")}</p>
              <div className="mt-1.5 flex items-center gap-2">
                <code className="flex-1 truncate rounded bg-canvas px-2.5 py-1.5 text-xs text-ink">{token}</code>
                <CopyButton value={token} title={t("kb.mcpCopy")} />
              </div>
              <button onClick={() => setToken(null)} className="mt-2 text-[12px] text-accent hover:underline">{t("kb.mcpBack")}</button>
            </div>
          )}

          <div className="mt-3 flex items-end gap-2">
            <label className="flex-1 text-sm font-medium text-ink">{t("kb.mcpKeyName")}
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder={t("kb.mcpKeyNamePh")} disabled={busy} className={`mt-1.5 ${field}`} /></label>
            <button onClick={onCreate} disabled={busy || !name.trim()} className="flex items-center gap-1 rounded-(--radius-control) bg-accent px-3 py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-50"><Plus className="size-4" /> {t("kb.mcpCreate")}</button>
          </div>
          <div className="mt-4 space-y-1.5">
            {keys.map((k) => (
              <div key={k.id} className="group/k flex items-center justify-between rounded-(--radius-control) border border-border/50 px-3 py-2 text-[13px]">
                <span className="text-ink">{k.name} <code className="ms-1 text-xs text-ink-faint">{k.token_prefix}…</code></span>
                <button onClick={() => onDelete(k)} className="rounded p-0.5 text-ink-faint opacity-0 transition hover:text-danger group-hover/k:opacity-100"><Trash className="size-3.5" /></button>
              </div>
            ))}
            {keys.length === 0 && <p className="py-2 text-center text-xs text-ink-faint">{t("kb.mcpNoKeys")}</p>}
          </div>
        </div>

        {/* Integration method tabs */}
        <div className="mt-5 flex gap-1.5 overflow-x-auto">
          <TabBtn k="mcp" label={t("kb.connTabMcp")} />
          <TabBtn k="dify" label={t("kb.connTabDify")} />
          <TabBtn k="api" label={t("kb.connTabApi")} />
        </div>

        <div className={`mt-3 ${card} space-y-4`}>
          {tab === "mcp" && (<>
            <Row label={t("kb.mcpEndpoint")} hint={t("kb.mcpEndpointHint")} value={mcpUrl} />
            <div>
              <p className="text-[12px] text-ink-faint">{t("kb.mcpConfigHint")}</p>
              <div className="mt-1.5"><Block value={mcpConfig} /></div>
            </div>
          </>)}

          {tab === "dify" && (<>
            <p className="text-[12px] leading-relaxed text-ink-secondary">{t("kb.difyHint")}</p>
            <Row label={t("kb.difyEndpoint")} value={extBase} />
            <Row label={t("kb.difyApiKey")} value={tok} />
            <Row label={t("kb.difyKnowledgeId")} hint={t("kb.difyKnowledgeIdHint")} value={id} />
          </>)}

          {tab === "api" && (<>
            <Row label={t("kb.apiSearchEndpoint")} hint={t("kb.apiSearchHint")} value={`${extBase}/search`} />
            <Row label={t("kb.apiOpenapi")} hint={t("kb.apiOpenapiHint")} value={`${extBase}/openapi.json`} />
            <div>
              <p className="text-[12px] text-ink-faint">{t("kb.apiCurlHint")}</p>
              <div className="mt-1.5"><Block value={curlSnippet} /></div>
            </div>
          </>)}
        </div>
      </div>
    </div>
  );
}
