/** 通用页码分页 —— 「显示 X–Y / 共 Z 条」+ 上一页/页码(带省略号)/下一页。紧凑精致。 */

import { CaretLeft, CaretRight } from "@phosphor-icons/react";
import { useTranslation } from "react-i18next";

/** 页码列表（带省略号）：1 … cur-1 cur cur+1 … total。 */
function pageList(cur: number, total: number): (number | "…")[] {
  const out: (number | "…")[] = [];
  for (let i = 1; i <= total; i++) {
    if (i === 1 || i === total || (i >= cur - 1 && i <= cur + 1)) out.push(i);
    else if (out[out.length - 1] !== "…") out.push("…");
  }
  return out;
}

interface PaginationProps {
  page: number;
  total: number;
  pageSize: number;
  onPage: (page: number) => void;
}

export function Pagination({ page, total, pageSize, onPage }: PaginationProps) {
  const { t } = useTranslation();
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);

  return (
    <div className="mt-3 flex items-center justify-between">
      <span className="text-xs text-ink-faint tabular-nums">
        {t("pagination.pageInfo", { from, to, total })}
      </span>
      {totalPages > 1 && (
        <div className="flex items-center gap-1">
          <PageBtn disabled={page <= 1} onClick={() => onPage(page - 1)} aria={t("pagination.prev")}>
            <CaretLeft className="size-3.5" />
          </PageBtn>
          {pageList(page, totalPages).map((p, i) =>
            p === "…" ? (
              <span key={`e${i}`} className="px-1 text-xs text-ink-faint">…</span>
            ) : (
              <button key={p} type="button" onClick={() => onPage(p)}
                className={`flex size-7 items-center justify-center rounded-(--radius-control) text-xs tabular-nums transition ${
                  p === page ? "bg-accent font-medium text-white"
                    : "text-ink-secondary hover:bg-surface hover:text-ink"}`}>
                {p}
              </button>
            ),
          )}
          <PageBtn disabled={page >= totalPages} onClick={() => onPage(page + 1)} aria={t("pagination.next")}>
            <CaretRight className="size-3.5" />
          </PageBtn>
        </div>
      )}
    </div>
  );
}

function PageBtn({ children, disabled, onClick, aria }: {
  children: React.ReactNode; disabled: boolean; onClick: () => void; aria: string;
}) {
  return (
    <button type="button" disabled={disabled} onClick={onClick} aria-label={aria}
      className="flex size-7 items-center justify-center rounded-(--radius-control) text-ink-secondary transition hover:bg-surface hover:text-ink disabled:cursor-not-allowed disabled:opacity-35 disabled:hover:bg-transparent">
      {children}
    </button>
  );
}
