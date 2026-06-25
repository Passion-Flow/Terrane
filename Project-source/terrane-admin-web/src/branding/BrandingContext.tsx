/** Branding context — fetches public branding on startup and globally provides product name / theme color / login subtitle.
 *  Side effects: the product name is written to document.title; the theme color overrides the --color-accent CSS variable trio.
 *  Falls back to factory defaults when absent (page-based zero-config); failures do not block rendering.
 *  After the settings page saves, invalidating ["branding"] refreshes it. */

import { useQuery } from "@tanstack/react-query";
import { createContext, useContext, useEffect, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { DEFAULT_BRANDING, getBranding, type Branding } from "@/lib/branding";

const BrandingContext = createContext<Branding>(DEFAULT_BRANDING);

export function useBranding(): Branding {
  return useContext(BrandingContext);
}

export function BrandingProvider({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const { data } = useQuery({
    queryKey: ["branding"],
    queryFn: getBranding,
    staleTime: 5 * 60_000,
  });
  const branding = data ?? DEFAULT_BRANDING;

  // Product name → tab title (keeps the "management console" suffix, which follows the language switch).
  useEffect(() => {
    document.title = `${branding.product_name} ${t("brand.console")}`;
  }, [branding.product_name, t]);

  // favicon: a dedicated favicon takes priority; otherwise fall back to the console Logo, then to the factory favicon.svg.
  useEffect(() => {
    const icon = branding.favicon ?? branding.logo_data;
    if (!icon) return;
    const link = document.querySelector<HTMLLinkElement>('link[rel="icon"]')
      ?? document.head.appendChild(Object.assign(document.createElement("link"), { rel: "icon" }));
    const prev = link.getAttribute("href");
    link.setAttribute("href", icon);
    link.removeAttribute("type");  // A data URI carries its own MIME type, so drop the hardcoded image/svg+xml
    return () => { if (prev) link.setAttribute("href", prev); };
  }, [branding.favicon, branding.logo_data]);

  // Theme color → override the accent CSS variables (hex takes priority; hover/soft follow the same color for a consistent look).
  useEffect(() => {
    const root = document.documentElement;
    const c = branding.accent_color;
    if (c && c !== DEFAULT_BRANDING.accent_color) {
      root.style.setProperty("--color-accent", c);
      root.style.setProperty("--color-accent-hover", c);
    } else {
      root.style.removeProperty("--color-accent");
      root.style.removeProperty("--color-accent-hover");
    }
  }, [branding.accent_color]);

  return <BrandingContext.Provider value={branding}>{children}</BrandingContext.Provider>;
}
