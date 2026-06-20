import i18next from "i18next";
import ICU from "i18next-icu";
import { initReactI18next } from "react-i18next";

import { FALLBACK_LANG, RTL_LANGS } from "@/i18n/langs";
import en from "@/i18n/locales/en/common.json";
import zhCN from "@/i18n/locales/zh-CN/common.json";

export const resources = {
  "zh-CN": { common: zhCN },
  en: { common: en },
} as const;

void i18next
  .use(ICU)
  .use(initReactI18next)
  .init({
    resources,
    lng: FALLBACK_LANG,
    fallbackLng: FALLBACK_LANG,
    defaultNS: "common",
    interpolation: { escapeValue: false },
  });

export function applyLang(lang: string): void {
  if (i18next.language !== lang) void i18next.changeLanguage(lang);
  document.documentElement.lang = lang;
  document.documentElement.dir = RTL_LANGS.has(lang) ? "rtl" : "ltr";
}

export default i18next;
