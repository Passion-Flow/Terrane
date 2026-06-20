/** 支持语言集（.agent.md [i18n]：locale 无关架构，支持增量加任意语言含 RTL）。
 * 首发 zh-CN + en（PRD §13.10：是否扩 23 语种为后续细化项；架构已就绪）。 */

export const SUPPORTED_LANGS = ["zh-CN", "en"] as const;
export type Lang = (typeof SUPPORTED_LANGS)[number];

export const FALLBACK_LANG: Lang = "zh-CN";

/** 下拉组件展示用：母语名 (母语地区)（i18n.md §4.6：必须下拉组件）。 */
export const LANG_LABELS: Record<Lang, string> = {
  "zh-CN": "简体中文",
  en: "English (United States)",
};

/** RTL 语言集（首发无，预留）。 */
export const RTL_LANGS: ReadonlySet<string> = new Set(["ar", "fa"]);

export function isSupported(lang: string): lang is Lang {
  return (SUPPORTED_LANGS as readonly string[]).includes(lang);
}

/** 根路径语言探测：浏览器语言 → 支持集匹配（精确 → 主语言段）→ fallback。 */
export function detectLang(candidates: readonly string[]): Lang {
  for (const candidate of candidates) {
    if (isSupported(candidate)) return candidate;
    const primary = candidate.split("-")[0];
    const match = SUPPORTED_LANGS.find((l) => l.split("-")[0] === primary);
    if (match) return match;
  }
  return FALLBACK_LANG;
}
