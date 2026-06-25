/** Polished Markdown rendering: GFM tables + KaTeX formulas + code / lists / blockquotes, aligned with the taste theme.
 *  Used for knowledge base source parsing previews, Studio text outputs, Wiki, etc. */
import "katex/dist/katex.min.css";

import ReactMarkdown, { type Components } from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

const components: Components = {
  h1: ({ node, ...p }) => <h1 className="mb-2 mt-5 text-lg font-semibold tracking-tight text-ink first:mt-0" {...p} />,
  h2: ({ node, ...p }) => <h2 className="mb-2 mt-4 border-b border-border/50 pb-1 text-base font-semibold text-ink first:mt-0" {...p} />,
  h3: ({ node, ...p }) => <h3 className="mb-1.5 mt-3 text-sm font-semibold text-ink" {...p} />,
  h4: ({ node, ...p }) => <h4 className="mb-1 mt-2 text-[13px] font-semibold text-ink" {...p} />,
  p: ({ node, ...p }) => <p className="my-2" {...p} />,
  ul: ({ node, ...p }) => <ul className="my-2 ms-5 list-disc space-y-1 marker:text-ink-faint" {...p} />,
  ol: ({ node, ...p }) => <ol className="my-2 ms-5 list-decimal space-y-1 marker:text-ink-faint" {...p} />,
  li: ({ node, ...p }) => <li className="pl-0.5" {...p} />,
  a: ({ node, ...p }) => <a className="text-accent underline underline-offset-2 transition hover:opacity-80" target="_blank" rel="noreferrer" {...p} />,
  strong: ({ node, ...p }) => <strong className="font-semibold text-ink" {...p} />,
  em: ({ node, ...p }) => <em className="italic" {...p} />,
  blockquote: ({ node, ...p }) => <blockquote className="my-3 border-s-2 border-accent/40 ps-3 text-ink-faint" {...p} />,
  hr: () => <hr className="my-4 border-border/60" />,
  code: ({ node, className, children, ...rest }) =>
    className
      ? <code className={className} {...rest}>{children}</code>
      : <code className="rounded bg-canvas px-1 py-0.5 text-[12px] text-accent" {...rest}>{children}</code>,
  pre: ({ node, ...p }) => <pre className="my-3 overflow-x-auto rounded-lg border border-border/60 bg-canvas p-3 text-[12px] leading-relaxed text-ink" {...p} />,
  table: ({ node, ...p }) => (
    <div className="my-3 overflow-x-auto rounded-lg border border-border/60">
      <table className="w-full border-collapse text-[12px]" {...p} />
    </div>
  ),
  thead: ({ node, ...p }) => <thead className="bg-surface/70" {...p} />,
  th: ({ node, ...p }) => <th className="whitespace-nowrap border-b border-border/60 px-3 py-1.5 text-start font-medium text-ink" {...p} />,
  td: ({ node, ...p }) => <td className="border-b border-border/40 px-3 py-1.5 align-top text-ink-secondary" {...p} />,
  img: ({ node, alt, ...p }) => <img className="my-3 max-w-full rounded-lg border border-border/50" alt={alt || ""} {...p} />,
};

export function Markdown({ children, className = "" }: { children: string; className?: string }) {
  return (
    <div className={`text-[13px] leading-relaxed text-ink-secondary ${className}`}>
      <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]} components={components}>
        {children}
      </ReactMarkdown>
    </div>
  );
}
