/** MCP 子页 —— 接入密钥管理(创建/列表/删除)。把这个知识库作为 MCP 工具挂进 Claude Code / Cursor。 */

import { Copy, Plus, Trash } from "@phosphor-icons/react";
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { useKb } from "@/components/KbLayout";
import { createMcpKey, deleteMcpKey, listMcpKeys, type McpKey } from "@/lib/kb";

export function McpPage() {
  const { t } = useTranslation();
  const { id } = useKb();
  const [keys, setKeys] = useState<McpKey[]>([]);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState<{ token: string; url: string } | null>(null);

  const load = useCallback(async () => { try { setKeys((await listMcpKeys(id)).items); } catch { /* */ } }, [id]);
  useEffect(() => { void load(); }, [load]);

  const origin = window.location.origin;
  // 按实际部署自动切换 scheme/host/port —— origin 已含 http(s) + IP/localhost/域名 + 非默认端口
  const mcpUrl = origin + "/mcp";

  async function onCreate() {
    if (!name.trim() || busy) return;
    setBusy(true);
    try { const r = await createMcpKey(id, name.trim()); setCreated({ token: r.token, url: origin + r.mcp_url }); setName(""); await load(); }
    finally { setBusy(false); }
  }
  async function onDelete(k: McpKey) {
    if (!window.confirm(t("kb.mcpDeleteConfirm", { name: k.name }))) return;
    try { await deleteMcpKey(id, k.id); await load(); } catch { /* */ }
  }
  const configSnippet = JSON.stringify(
    { mcpServers: { terrane: { url: created?.url ?? mcpUrl, headers: { Authorization: `Bearer ${created?.token ?? "<YOUR_TOKEN>"}` } } } },
    null, 2,
  );
  const field = "w-full rounded-(--radius-control) border border-border bg-canvas px-3 py-2 text-sm text-ink outline-none focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/30";

  return (
    <div className="px-6 py-8 sm:px-8">
      <div className="mx-auto max-w-3xl">
        <h1 className="text-2xl font-bold tracking-tight text-ink">{t("kb.mcpTitle")}</h1>
        <p className="mt-1 text-sm text-ink-secondary">{t("kb.mcpDesc")}</p>

        <div className="mt-6 rounded-(--radius-card) border border-border/70 bg-surface/40 p-5">
          <p className="text-[13px] font-medium text-ink">{t("kb.mcpEndpoint")}</p>
          <p className="mt-1 text-[12px] text-ink-faint">{t("kb.mcpEndpointHint")}</p>
          <div className="mt-2 flex items-center gap-2">
            <code className="flex-1 truncate rounded bg-canvas px-2.5 py-1.5 text-xs text-ink">{mcpUrl}</code>
            <button onClick={() => navigator.clipboard?.writeText(mcpUrl)} title={t("kb.mcpCopy")} className="rounded p-1.5 text-ink-secondary hover:bg-canvas"><Copy className="size-4" /></button>
          </div>
        </div>

        <div className="mt-4 rounded-(--radius-card) border border-border/70 bg-surface/40 p-5">
          {created ? (
            <div className="space-y-2">
              <p className="text-[13px] font-medium text-danger">{t("kb.mcpTokenOnce")}</p>
              <div className="flex items-center gap-2">
                <code className="flex-1 truncate rounded bg-canvas px-2 py-1.5 text-xs text-ink">{created.token}</code>
                <button onClick={() => navigator.clipboard?.writeText(created.token)} className="rounded p-1.5 text-ink-secondary hover:bg-canvas"><Copy className="size-4" /></button>
              </div>
              <p className="mt-2 text-[12px] text-ink-faint">{t("kb.mcpConfigHint")}</p>
              <div className="relative">
                <pre className="max-h-48 overflow-auto rounded-(--radius-control) bg-canvas p-3 text-[11px] leading-relaxed text-ink-secondary">{configSnippet}</pre>
                <button onClick={() => navigator.clipboard?.writeText(configSnippet)} className="absolute end-2 top-2 rounded bg-surface p-1 text-ink-secondary hover:text-ink"><Copy className="size-3.5" /></button>
              </div>
              <button onClick={() => setCreated(null)} className="text-[13px] text-accent hover:underline">{t("kb.mcpBack")}</button>
            </div>
          ) : (
            <>
              <div className="flex items-end gap-2">
                <label className="flex-1 text-sm font-medium text-ink">{t("kb.mcpKeyName")}
                  <input value={name} onChange={(e) => setName(e.target.value)} placeholder={t("kb.mcpKeyNamePh")} disabled={busy} className={`mt-1.5 ${field}`} /></label>
                <button onClick={onCreate} disabled={busy || !name.trim()} className="flex items-center gap-1 rounded-(--radius-control) bg-accent px-3 py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-50"><Plus className="size-4" /> {t("kb.mcpCreate")}</button>
              </div>
              <div className="mt-5 space-y-1.5">
                {keys.map((k) => (
                  <div key={k.id} className="group/k flex items-center justify-between rounded-(--radius-control) border border-border/50 px-3 py-2 text-[13px]">
                    <span className="text-ink">{k.name} <code className="ms-1 text-xs text-ink-faint">{k.token_prefix}…</code></span>
                    <button onClick={() => onDelete(k)} className="rounded p-0.5 text-ink-faint opacity-0 transition hover:text-danger group-hover/k:opacity-100"><Trash className="size-3.5" /></button>
                  </div>
                ))}
                {keys.length === 0 && <p className="py-2 text-center text-xs text-ink-faint">{t("kb.mcpNoKeys")}</p>}
              </div>
              <div className="mt-5 border-t border-border/50 pt-4">
                <p className="text-[12px] text-ink-faint">{t("kb.mcpConfigHint")}</p>
                <div className="relative mt-2">
                  <pre className="max-h-48 overflow-auto rounded-(--radius-control) bg-canvas p-3 text-[11px] leading-relaxed text-ink-secondary">{configSnippet}</pre>
                  <button onClick={() => navigator.clipboard?.writeText(configSnippet)} title={t("kb.mcpCopy")} className="absolute end-2 top-2 rounded bg-surface p-1 text-ink-secondary hover:text-ink"><Copy className="size-3.5" /></button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
