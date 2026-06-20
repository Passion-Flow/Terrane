/** 语言切换 —— 自定义下拉组件（i18n.md §4.6：必须下拉、列母语名、非原生 select）。
 *  切换即改 URL 的 /<lang>/ 前缀（路由层 applyLang 生效）。 */

import { Check, CaretDown, GlobeHemisphereWest } from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate, useParams } from "react-router";

import { FALLBACK_LANG, isSupported, LANG_LABELS, SUPPORTED_LANGS, type Lang } from "@/i18n/langs";

export function LanguageSelect() {
  const { t } = useTranslation();
  const { lang } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const current: Lang = lang && isSupported(lang) ? lang : FALLBACK_LANG;

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  const pick = (next: Lang) => {
    setOpen(false);
    if (next === current) return;
    // 替换 URL 首段语言码，保留其余路径。
    const rest = location.pathname.replace(/^\/[^/]+/, "");
    navigate(`/${next}${rest}${location.search}`, { replace: true });
  };

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        aria-label={t("lang.label")}
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 rounded-full border border-border px-3 py-1.5 text-[13px] text-ink hover:bg-surface focus-visible:ring-2 focus-visible:ring-accent"
      >
        <GlobeHemisphereWest size={16} className="text-ink-secondary" />
        <span>{LANG_LABELS[current]}</span>
        <CaretDown size={13} className="text-ink-faint" />
      </button>
      {open && (
        <div className="absolute end-0 z-50 mt-1.5 min-w-44 rounded-(--radius-control) border border-border bg-surface py-1 shadow-lg">
          {SUPPORTED_LANGS.map((code) => (
            <button
              key={code}
              type="button"
              onClick={() => pick(code)}
              className="flex w-full items-center gap-2.5 px-3 py-2 text-sm text-ink hover:bg-canvas"
            >
              <span className="flex-1 text-start">{LANG_LABELS[code]}</span>
              {current === code && <Check size={15} className="text-accent" />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
