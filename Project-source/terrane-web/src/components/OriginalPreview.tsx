/** Renders the original of a knowledge base source: PDF (iframe) / image / Excel (SheetJS → table) / Word (docx-preview) /
 *  text md·txt·csv (raw) / others (download). xlsx and docx-preview are lazy-loaded. */
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { apiBase } from "@/lib/config";

const isPdf = (m?: string | null) => !!m && m.includes("pdf");
const isImage = (m?: string | null) => !!m && m.startsWith("image/");
const isXlsx = (m?: string | null, n?: string) => /spreadsheet|ms-excel/.test(m || "") || /\.(xlsx|xls)$/i.test(n || "");
const isDocx = (m?: string | null, n?: string) => /wordprocessingml/.test(m || "") || /\.docx$/i.test(n || "");
const isText = (m?: string | null, n?: string) =>
  (!!m && m.startsWith("text/")) || /json|xml|yaml|csv|markdown/.test(m || "") ||
  /\.(md|markdown|txt|csv|tsv|json|log|ya?ml|ini|conf)$/i.test(n || "");

type Kind = "loading" | "pdf" | "image" | "text" | "xlsx" | "docx" | "download" | "error";

export function OriginalPreview({ kbId, sourceId, mime, title }: { kbId: string; sourceId: string; mime: string | null; title: string }) {
  const { t } = useTranslation();
  const [kind, setKind] = useState<Kind>("loading");
  const [url, setUrl] = useState("");
  const [text, setText] = useState("");
  const [sheetHtml, setSheetHtml] = useState("");
  const docxRef = useRef<HTMLDivElement>(null);
  const docxBlob = useRef<Blob | null>(null);

  useEffect(() => {
    let obj: string | null = null;
    let cancelled = false;
    setKind("loading");
    (async () => {
      try {
        const resp = await fetch(`${apiBase()}/api/v1/knowledge-bases/${kbId}/sources/${sourceId}/original`, { credentials: "include" });
        if (!resp.ok) throw new Error("no original");
        const blob = await resp.blob();
        if (cancelled) return;
        if (isPdf(mime)) { obj = URL.createObjectURL(blob); setUrl(obj); setKind("pdf"); }
        else if (isImage(mime)) { obj = URL.createObjectURL(blob); setUrl(obj); setKind("image"); }
        else if (isXlsx(mime, title)) {
          const XLSX = await import("xlsx");
          const wb = XLSX.read(await blob.arrayBuffer(), { type: "array" });
          const html = wb.SheetNames.map((n) => `<div class="trn-sheet">${n}</div>` + XLSX.utils.sheet_to_html(wb.Sheets[n])).join("");
          if (!cancelled) { setSheetHtml(html); setKind("xlsx"); }
        }
        else if (isDocx(mime, title)) { docxBlob.current = blob; if (!cancelled) setKind("docx"); }
        else if (isText(mime, title)) { const txt = await blob.text(); if (!cancelled) { setText(txt); setKind("text"); } }
        else { obj = URL.createObjectURL(blob); setUrl(obj); setKind("download"); }
      } catch { if (!cancelled) setKind("error"); }
    })();
    return () => { cancelled = true; if (obj) URL.revokeObjectURL(obj); };
  }, [kbId, sourceId, mime, title]);

  // Word: docx-preview renders asynchronously into the container
  useEffect(() => {
    if (kind !== "docx" || !docxRef.current || !docxBlob.current) return;
    const el = docxRef.current;
    import("docx-preview").then(({ renderAsync }) => {
      el.innerHTML = "";
      renderAsync(docxBlob.current!, el, undefined, { inWrapper: false, ignoreWidth: true, ignoreHeight: true, ignoreLastRenderedPageBreak: true }).catch(() => setKind("error"));
    }).catch(() => setKind("error"));
  }, [kind]);

  if (kind === "loading") return <div className="flex h-full items-center justify-center text-xs text-ink-faint">{t("common.loading")}</div>;
  if (kind === "error") return <div className="flex h-full items-center justify-center text-xs text-ink-faint">{t("kb.previewOriginalFail", { defaultValue: "Failed to load original" })}</div>;
  if (kind === "pdf") return <iframe src={url} title="original" className="h-full w-full border-0" />;
  if (kind === "image") return <div className="flex min-h-full items-center justify-center p-3"><img src={url} alt={title} className="max-w-full" /></div>;
  if (kind === "text") return <pre className="whitespace-pre-wrap break-words p-4 font-mono text-[12px] leading-relaxed text-ink-secondary">{text}</pre>;
  if (kind === "xlsx") return (
    <div className="p-3 text-[12px] [&_.trn-sheet]:mb-1.5 [&_.trn-sheet]:mt-3 [&_.trn-sheet]:font-semibold [&_.trn-sheet]:text-ink [&_table]:mb-2 [&_table]:w-full [&_table]:border-collapse [&_td]:border [&_td]:border-border/40 [&_td]:px-2 [&_td]:py-1 [&_td]:text-ink-secondary"
      dangerouslySetInnerHTML={{ __html: sheetHtml }} />
  );
  if (kind === "docx") return <div ref={docxRef} className="p-4 text-[13px] text-ink [&_*]:!max-w-full [&_img]:rounded" />;
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 px-4 text-center">
      <p className="text-xs text-ink-faint">{t("kb.previewNoRender")}</p>
      <a href={url} download={title} className="text-xs text-accent underline">{t("kb.downloadOriginal")}</a>
    </div>
  );
}
