/** Branding context (frontend) — fetches public branding on startup, globally providing
 *  product name / theme color / login subtitle / logo.
 *  Side effects: product name → document.title; theme color → overrides --color-accent;
 *  custom logo → favicon.
 *  Falls back to factory defaults when absent (page-based zero-config); failures do not block rendering. */

import { useQuery } from "@tanstack/react-query";
import { createContext, useContext, useEffect, type ReactNode } from "react";

import { DEFAULT_BRANDING, getBranding, type Branding } from "@/lib/branding";

const BrandingContext = createContext<Branding>(DEFAULT_BRANDING);

export function useBranding(): Branding {
  return useContext(BrandingContext);
}

export function BrandingProvider({ children }: { children: ReactNode }) {
  const { data } = useQuery({
    queryKey: ["branding"],
    queryFn: getBranding,
    staleTime: 5 * 60_000,
  });
  const branding = data ?? DEFAULT_BRANDING;

  // Product name → tab title.
  useEffect(() => {
    document.title = branding.product_name;
  }, [branding.product_name]);

  // Theme color → overrides the accent CSS variable (hex takes priority; hover follows the same color).
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

  // favicon: a dedicated favicon takes priority, falling back to the console logo, then keeping the factory favicon.svg.
  useEffect(() => {
    const icon = branding.favicon ?? branding.logo_data;
    if (!icon) return;
    const link = document.querySelector<HTMLLinkElement>('link[rel="icon"]')
      ?? document.head.appendChild(Object.assign(document.createElement("link"), { rel: "icon" }));
    const prev = link.getAttribute("href");
    link.setAttribute("href", icon);
    link.removeAttribute("type");
    return () => { if (prev) link.setAttribute("href", prev); };
  }, [branding.favicon, branding.logo_data]);

  return <BrandingContext.Provider value={branding}>{children}</BrandingContext.Provider>;
}
