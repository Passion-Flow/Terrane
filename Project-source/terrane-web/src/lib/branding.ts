/** Public branding (white-label) API (/api/v1/branding) — no login required, accessible while locked.
 *  Lets the frontend show the deployer's branding (logo / tab title / login subtitle) before authentication. */

import { request } from "@/lib/api";

export interface Branding {
  product_name: string;
  logo_data: string | null;     // Console / workspace logo
  login_logo: string | null;    // Login page logo
  favicon: string | null;       // Site favicon
  accent_color: string;
  login_subtitle: string | null;
  support_url: string | null;
  enabled: boolean;
}

export const DEFAULT_BRANDING: Branding = {
  product_name: "Terrane",
  logo_data: null,
  login_logo: null,
  favicon: null,
  accent_color: "#0f9b8e",
  login_subtitle: null,
  support_url: null,
  enabled: true,
};

export function getBranding(): Promise<Branding> {
  return request<Branding>("/api/v1/branding", { credentials: "include" });
}
