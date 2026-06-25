/** Supported language set (.agent.md [i18n]: locale-agnostic architecture, supports
 * incrementally adding any language including RTL).
 * Launches with zh-CN + en (PRD §13.10: expanding to 23 languages is a follow-up item;
 * the architecture is already in place). */

export const SUPPORTED_LANGS = ["zh-CN", "en"] as const;
export type Lang = (typeof SUPPORTED_LANGS)[number];

export const FALLBACK_LANG: Lang = "zh-CN";

/** For display in the dropdown component: native name (native region) (i18n.md §4.6: must be a dropdown component). */
export const LANG_LABELS: Record<Lang, string> = {
  "zh-CN": "简体中文",
  en: "English (United States)",
};

/** RTL language set (none at launch, reserved for future use). */
export const RTL_LANGS: ReadonlySet<string> = new Set(["ar", "fa"]);

export function isSupported(lang: string): lang is Lang {
  return (SUPPORTED_LANGS as readonly string[]).includes(lang);
}

/** Root-path language detection: browser language → match against supported set (exact → primary subtag) → fallback. */
export function detectLang(candidates: readonly string[]): Lang {
  for (const candidate of candidates) {
    if (isSupported(candidate)) return candidate;
    const primary = candidate.split("-")[0];
    const match = SUPPORTED_LANGS.find((l) => l.split("-")[0] === primary);
    if (match) return match;
  }
  return FALLBACK_LANG;
}
