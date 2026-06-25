/** Public branding (white-label) API (/admin-api/v1/branding) — no login required, available in the locked state.
 *  Lets the Logo / login page / title bar show the deployer's branding before authentication (product name / theme color / login subtitle). */

import { request } from "@/lib/api";

export interface Branding {
  product_name: string;
  logo_data: string | null;     // Console / workspace Logo
  login_logo: string | null;    // Login page Logo
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
  return request<Branding>("/admin-api/v1/branding", { credentials: "include" });
}
