/** 复制按钮 —— 点击复制 value,成功后短暂显示 ✓ 反馈。兼容 HTTP 非安全上下文(见 lib/clipboard)。 */

import { Check, Copy } from "@phosphor-icons/react";
import { useState } from "react";

import { copyText } from "@/lib/clipboard";

export function CopyButton({
  value,
  title,
  className = "rounded p-1.5 text-ink-secondary transition hover:bg-canvas hover:text-ink",
  iconClassName = "size-4",
}: {
  value: string;
  title?: string;
  className?: string;
  iconClassName?: string;
}) {
  const [done, setDone] = useState(false);

  async function onClick() {
    const ok = await copyText(value);
    if (ok) {
      setDone(true);
      window.setTimeout(() => setDone(false), 1500);
    }
  }

  return (
    <button type="button" onClick={() => void onClick()} title={title} aria-label={title} className={className}>
      {done
        ? <Check className={`${iconClassName} text-emerald-500`} weight="bold" />
        : <Copy className={iconClassName} />}
    </button>
  );
}
